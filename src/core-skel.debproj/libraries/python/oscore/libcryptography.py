import hashlib
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# ---------------------------------------------------------
# Helper: Deterministic Random Number Generator
# ---------------------------------------------------------
class DeterministicRNG:
    """
    A specific RNG wrapper to make RSA key generation deterministic
    based on a seed.
    """
    def __init__(self, seed):
        # Initialize with a strong hash of the seed
        if isinstance(seed, str):
            seed = seed.encode('utf-8')
        self.state = hashlib.sha256(seed).digest()
        self.counter = 0

    def read(self, n):
        """Generates n bytes deterministically based on the initial seed."""
        output = b""
        while len(output) < n:
            # Update state with counter to generate new blocks
            data_to_hash = self.state + self.counter.to_bytes(8, 'big')
            block = hashlib.sha256(data_to_hash).digest()
            output += block
            self.counter += 1
        return output[:n]

# ---------------------------------------------------------
# Core Functions
# ---------------------------------------------------------

def keygen(seed=None, symmetric: bool = False):
    """
    Generates a key for the specified algorithm.

    Args:
        :param seed (optional): A string or bytes. If provided, the same seed
                         will always produce the same key.
        :param algorithm (str): 'AES' (default) or 'RSA'
    """
    algorithm = 'RSA' if not symmetric else 'AES'
    algorithm = algorithm.upper()

    if algorithm == 'AES':
        if seed:
            # Deterministic: Hash the seed to get a 32-byte (256-bit) key
            if isinstance(seed, str):
                seed = seed.encode()
            return hashlib.sha256(seed).digest()
        else:
            # Random: Generate random 32 bytes
            return get_random_bytes(32)

    elif algorithm == 'RSA':
        key_size = 2048
        if seed:
            # Deterministic: Use custom RNG seeded with input
            rng = DeterministicRNG(seed)
            key = RSA.generate(key_size, randfunc=rng.read)
        else:
            # Random: Standard generation
            key = RSA.generate(key_size)
        return key

    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def encrypt(content, key, symmetric: bool = False):
    """
    Encrypts content using the provided key and algorithm.
    """

    algorithm = 'RSA' if not symmetric else 'AES'

    algorithm = algorithm.upper()

    # Ensure content is bytes
    if isinstance(content, str):
        content = content.encode('utf-8')

    if algorithm == 'AES':
        # Using AES-CBC mode
        # key must be bytes
        iv = get_random_bytes(16) # Initialization Vector
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(content, AES.block_size))
        # Return IV + Ciphertext so we can decrypt later
        return iv + ciphertext

    elif algorithm == 'RSA':
        # RSA encryption uses the PUBLIC key
        # If a private key object is passed, extract the public part
        if key.has_private():
            public_key = key.publickey()
        else:
            public_key = key

        cipher = PKCS1_OAEP.new(public_key)
        return cipher.encrypt(content)

    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def decrypt(content, key, symmetric: bool = False):
    """
    Decrypts content using the provided key and algorithm.
    """

    algorithm = 'RSA' if not symmetric else 'AES'

    algorithm = algorithm.upper()

    if algorithm == 'AES':
        # Extract IV (first 16 bytes) and Ciphertext
        iv = content[:16]
        ciphertext = content[16:]

        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return plaintext.decode('utf-8')

    elif algorithm == 'RSA':
        # RSA decryption requires the PRIVATE key
        if not key.has_private():
            raise ValueError("RSA decryption requires a private key.")

        cipher = PKCS1_OAEP.new(key)
        plaintext = cipher.decrypt(content)
        return plaintext.decode('utf-8')

    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")