import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BRIDGE_PROCESS_NAME = 'clipboardd';
const BRIDGE_PUSH_IPC_ID = 'push_text';
const DEFAULT_LIBIPC_DIR_NAME = 'clipboardd-libipc';
const MAX_TEXT_BYTES = 512 * 1024;
const MAX_IMAGE_BYTES = 16 * 1024 * 1024;
const READ_DEBOUNCE_MSEC = 75;
const LIBIPC_MAX_REPLY_BYTES = 64 * 1024;
const IMAGE_MIME_TYPES = [
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/webp',
    'image/gif',
    'image/bmp',
    'image/tiff',
    'image/svg+xml',
];

export default class ClipboardHelperExtension extends Extension {
    enable() {
        this._clipboard = St.Clipboard.get_default();
        this._selection = Shell.Global.get().get_display().get_selection();
        this._selectionOwnerChangedId = 0;
        this._readTimeoutId = 0;
        this._lastAcceptedKey = null;
        this._textEncoder = new TextEncoder();
        this._textDecoder = new TextDecoder();
        this._bridgeCancellable = new Gio.Cancellable();

        this._selectionOwnerChangedId = this._selection.connect(
            'owner-changed',
            (_selection, selectionType) => {
                if (selectionType !== Meta.SelectionType.SELECTION_CLIPBOARD)
                    return;

                this._scheduleClipboardRead();
            }
        );
    }

    disable() {
        if (this._readTimeoutId) {
            GLib.Source.remove(this._readTimeoutId);
            this._readTimeoutId = 0;
        }

        if (this._selectionOwnerChangedId && this._selection) {
            this._selection.disconnect(this._selectionOwnerChangedId);
            this._selectionOwnerChangedId = 0;
        }

        this._selection = null;
        this._clipboard = null;
        this._lastAcceptedKey = null;
        this._textEncoder = null;
        this._textDecoder = null;

        if (this._bridgeCancellable) {
            this._bridgeCancellable.cancel();
            this._bridgeCancellable = null;
        }
    }

    _scheduleClipboardRead() {
        if (this._readTimeoutId)
            GLib.Source.remove(this._readTimeoutId);

        this._readTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            READ_DEBOUNCE_MSEC,
            () => {
                this._readTimeoutId = 0;
                this._readClipboardText();
                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _readClipboardText() {
        try {
            this._clipboard.get_text(St.ClipboardType.CLIPBOARD, (_clipboard, text) => {
                try {
                    if (!this._handleClipboardText(text))
                        this._readClipboardImage();
                } catch (error) {
                    this._logSafeFailure('clipboard handling failed', error);
                }
            });
        } catch (error) {
            this._logSafeFailure('clipboard read failed', error);
        }
    }

    _handleClipboardText(text) {
        if (typeof text !== 'string')
            return false;

        if (text.trim().length === 0)
            return false;

        const byteLength = this._textEncoder.encode(text).length;
        if (byteLength > MAX_TEXT_BYTES) {
            this._logSafeFailure(`clipboard text rejected: ${byteLength} bytes exceeds limit`, null);
            return true;
        }

        const hash = GLib.compute_checksum_for_string(
            GLib.ChecksumType.SHA256,
            text,
            -1
        );
        const key = `text:text/plain:${hash}`;

        if (key === this._lastAcceptedKey)
            return true;

        this._lastAcceptedKey = key;
        this.pushToBridge({
            kind: 'text',
            mime_type: 'text/plain',
            text,
            size_bytes: byteLength,
        });
        return true;
    }

    _readClipboardImage() {
        let mimetypes;
        try {
            mimetypes = this._clipboard.get_mimetypes(St.ClipboardType.CLIPBOARD) || [];
        } catch (error) {
            this._logSafeFailure('clipboard mimetype read failed', error);
            return;
        }

        const mimeType = IMAGE_MIME_TYPES.find(type => mimetypes.includes(type));
        if (!mimeType)
            return;

        try {
            this._clipboard.get_content(
                St.ClipboardType.CLIPBOARD,
                mimeType,
                (_clipboard, bytes) => {
                    try {
                        this._handleClipboardImage(mimeType, bytes);
                    } catch (error) {
                        this._logSafeFailure('clipboard image handling failed', error);
                    }
                }
            );
        } catch (error) {
            this._logSafeFailure('clipboard image read failed', error);
        }
    }

    _handleClipboardImage(mimeType, bytes) {
        if (!bytes)
            return;

        const sizeBytes = bytes.get_size();
        if (sizeBytes <= 0)
            return;

        if (sizeBytes > MAX_IMAGE_BYTES) {
            this._logSafeFailure(`clipboard image rejected: ${sizeBytes} bytes exceeds limit`, null);
            return;
        }

        const data = bytes.get_data();
        const hash = GLib.compute_checksum_for_data(GLib.ChecksumType.SHA256, data);
        const key = `image:${mimeType}:${hash}`;
        if (key === this._lastAcceptedKey)
            return;

        this._lastAcceptedKey = key;
        this.pushToBridge({
            kind: 'image',
            mime_type: mimeType,
            data_b64: GLib.base64_encode(data),
            size_bytes: sizeBytes,
        });
    }

    pushToBridge(payload) {
        const socketPaths = this._findBridgeSocketPaths();
        if (!socketPaths.length) {
            this._logSafeFailure('bridge socket not found', null);
            return;
        }

        this._pushToBridgeSocket(payload, socketPaths, 0, null);
    }

    _pushToBridgeSocket(payload, socketPaths, index, lastError) {
        if (index >= socketPaths.length) {
            this._logSafeFailure('bridge call failed for all sockets', lastError);
            return;
        }

        const socketPath = socketPaths[index];

        try {
            const address = new Gio.UnixSocketAddress({path: socketPath});
            const client = new Gio.SocketClient({timeout: 1});

            client.connect_async(
                address,
                this._bridgeCancellable,
                (socketClient, result) => {
                    let connection = null;
                    try {
                        connection = socketClient.connect_finish(result);
                        connection.get_socket().set_timeout(1);

                        const output = connection.get_output_stream();
                        const input = connection.get_input_stream();
                        const message = this._encodeLibipcMessage(payload);

                        output.write_all(message, null);
                        output.flush(null);
                        this._readLibipcReply(input);
                    } catch (error) {
                        this._pushToBridgeSocket(payload, socketPaths, index + 1, error);
                    } finally {
                        if (connection) {
                            try {
                                connection.close(null);
                            } catch (_error) {
                                // ignore close failures
                            }
                        }
                    }
                }
            );
        } catch (error) {
            this._logSafeFailure('bridge call setup failed', error);
        }
    }

    _findBridgeSocketPaths() {
        const socketDirs = [
            GLib.getenv('LIBIPC_SOCK_DIR'),
            GLib.build_filenamev([GLib.get_user_runtime_dir(), DEFAULT_LIBIPC_DIR_NAME]),
            '/tmp/libipc',
        ].filter(path => path);

        const matches = [];

        for (const socketDir of socketDirs)
            this._collectBridgeSocketMatches(socketDir, matches);

        matches.sort();
        return matches.reverse();
    }

    _collectBridgeSocketMatches(socketDir, matches) {

        if (!GLib.file_test(socketDir, GLib.FileTest.IS_DIR))
            return;

        const directory = Gio.File.new_for_path(socketDir);

        let enumerator = null;
        try {
            enumerator = directory.enumerate_children(
                'standard::name,standard::type',
                Gio.FileQueryInfoFlags.NONE,
                null
            );

            let info;
            while ((info = enumerator.next_file(null)) !== null) {
                if (info.get_file_type() !== Gio.FileType.SPECIAL)
                    continue;

                const name = info.get_name();
                if (name.startsWith(`${BRIDGE_PROCESS_NAME}_`) &&
                    name.includes(`_${BRIDGE_PUSH_IPC_ID}_`) &&
                    name.endsWith('.sock')) {
                    matches.push(GLib.build_filenamev([socketDir, name]));
                }
            }
        } catch (error) {
            this._logSafeFailure('bridge socket scan failed', error);
        } finally {
            if (enumerator) {
                try {
                    enumerator.close(null);
                } catch (_error) {
                    // ignore close failures
                }
            }
        }
    }

    _encodeLibipcMessage(data) {
        const payload = this._textEncoder.encode(JSON.stringify({
            from: null,
            data,
        }));
        const message = new Uint8Array(4 + payload.length);

        message[0] = (payload.length >>> 24) & 0xff;
        message[1] = (payload.length >>> 16) & 0xff;
        message[2] = (payload.length >>> 8) & 0xff;
        message[3] = payload.length & 0xff;
        message.set(payload, 4);

        return message;
    }

    _readLibipcReply(input) {
        const header = this._readExact(input, 4);
        const length =
            (header[0] << 24) |
            (header[1] << 16) |
            (header[2] << 8) |
            header[3];

        if (length <= 0 || length > LIBIPC_MAX_REPLY_BYTES)
            throw new Error('invalid bridge reply length');

        const payload = this._readExact(input, length);
        const reply = JSON.parse(this._textDecoder.decode(payload));

        if (!reply.ok)
            throw new Error(reply.error || 'bridge rejected message');
    }

    _readExact(input, length) {
        const bytes = input.read_bytes(length, null);
        const data = bytes.get_data();

        if (data.length !== length)
            throw new Error('short bridge reply');

        return data;
    }

    _logSafeFailure(message, error) {
        const detail = error?.message ? `: ${error.message}` : '';
        console.warn(`[${this.uuid}] ${message}${detail}`);
    }
}
