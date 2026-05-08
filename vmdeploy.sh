#!/usr/bin/env bash
# test-pipeline.sh — VM 롤백 + 호스트 빌드 병렬 실행 후 배포·설치·재시동

set -Eeuo pipefail

# ───── 고정값 ─────
VM_NAME="Ubuntu 64-bit"
SNAPSHOT_NAME="clean-slate"
OUTPUT_DIR="output"
REMOTE_STAGING="/tmp/outputs"
SSH_WAIT_TIMEOUT=180

# ⚠️ 임시 자격증명: 이 스크립트는 신뢰된 로컬 환경에서만 사용하세요.
VM_PASSWORD="1111"

# ───── 로깅 유틸 ─────
ts()   { date '+%H:%M:%S'; }
log()  { printf '\e[1;34m[%s]\e[0m %s\n'        "$(ts)" "$*"; }
warn() { printf '\e[1;33m[%s] WARN:\e[0m %s\n'  "$(ts)" "$*" >&2; }
fail() { printf '\e[1;31m[%s] ERROR:\e[0m %s\n' "$(ts)" "$*" >&2; exit 1; }

# 사전 검사
command -v vmrun   >/dev/null || fail "vmrun을 PATH에서 찾을 수 없습니다 (VMware Workstation 설치 확인)"
command -v ssh     >/dev/null || fail "ssh가 필요합니다"
command -v scp     >/dev/null || fail "scp가 필요합니다"
command -v sshpass >/dev/null || fail "sshpass가 필요합니다 (sudo apt install sshpass)"

# ───── 자동 감지: .vmx 경로 ─────
log "'$VM_NAME'의 .vmx 파일 검색 중..."
VMX_SEARCH_PATHS=(
  "$HOME/vmware"
  "$HOME/Documents/Virtual Machines"
  "$HOME/Virtual Machines"
)

VMX_PATH=""
# 1순위: 현재 실행 중인 VM 목록에서 찾기
while IFS= read -r running_vmx; do
  [[ -z "$running_vmx" ]] && continue
  if [[ "$(basename "$running_vmx" .vmx)" == "$VM_NAME" ]]; then
    VMX_PATH="$running_vmx"
    break
  fi
done < <(vmrun -T ws list 2>/dev/null | tail -n +2)

# 2순위: 일반적인 경로에서 검색 (공백 포함 경로 안전)
if [[ -z "$VMX_PATH" ]]; then
  for base in "${VMX_SEARCH_PATHS[@]}"; do
    [[ -d "$base" ]] || continue
    while IFS= read -r -d '' found; do
      VMX_PATH="$found"
      break 2
    done < <(find "$base" -maxdepth 4 -type f -name "${VM_NAME}.vmx" -print0 2>/dev/null)
  done
fi

[[ -n "$VMX_PATH" && -f "$VMX_PATH" ]] \
  || fail ".vmx 파일을 찾지 못했습니다. VM 이름이 '${VM_NAME}'인지, 일반 경로($HOME/vmware 등)에 있는지 확인하세요"
log "VMX 경로: $VMX_PATH"

# 스냅샷 존재 확인
if ! vmrun -T ws listSnapshots "$VMX_PATH" 2>/dev/null | tail -n +2 | grep -qxF "$SNAPSHOT_NAME"; then
  fail "'$SNAPSHOT_NAME' 스냅샷이 VM에 존재하지 않습니다"
fi

# ───── 자동 감지: SSH 사용자 ─────
VM_USER="${USER:-$(id -un)}"
log "SSH 사용자: $VM_USER (호스트 사용자명 사용)"

# sshpass에 비밀번호를 환경변수로 전달 (커맨드라인 -p는 ps에 노출되므로 지양)
SSH_OPTS=(-o StrictHostKeyChecking=accept-new
          -o UserKnownHostsFile="$HOME/.ssh/known_hosts"
          -o PubkeyAuthentication=no
          -o PreferredAuthentications=password
          -o ConnectTimeout=5
          -o ServerAliveInterval=15)
SCP_OPTS=("${SSH_OPTS[@]}" -r)

ssh_vm() { SSHPASS="$VM_PASSWORD" sshpass -e ssh "${SSH_OPTS[@]}" "$@"; }
scp_vm() { SSHPASS="$VM_PASSWORD" sshpass -e scp "${SCP_OPTS[@]}" "$@"; }

# ───── VM IP 자동 감지 ─────
detect_vm_ip() {
  local deadline=$((SECONDS + SSH_WAIT_TIMEOUT))
  local ip=""
  while (( SECONDS < deadline )); do
    ip="$(vmrun -T ws getGuestIPAddress "$VMX_PATH" -wait 2>/dev/null || true)"
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "$ip"
      return 0
    fi
    sleep 3
  done
  return 1
}

# 임시 파일 및 백그라운드 작업 정리
VM_IP_FILE="$(mktemp)"
cleanup() {
  local rc=$?
  if [[ -n "${ROLLBACK_PID:-}" ]] && kill -0 "$ROLLBACK_PID" 2>/dev/null; then
    warn "롤백 작업($ROLLBACK_PID) 종료 중..."
    kill "$ROLLBACK_PID" 2>/dev/null || true
    wait "$ROLLBACK_PID" 2>/dev/null || true
  fi
  rm -f "$VM_IP_FILE"
  exit $rc
}
trap cleanup EXIT INT TERM

# ───── 1단계: VM 롤백(백그라운드) + 호스트 빌드(포그라운드) 동시 진행 ─────
rollback_vm() {
  echo "스냅샷 '$SNAPSHOT_NAME'(으)로 롤백"
  vmrun -T ws revertToSnapshot "$VMX_PATH" "$SNAPSHOT_NAME"
  echo "VM 시동 (GUI)"
  vmrun -T ws start "$VMX_PATH"

  echo "게스트 IP 감지 대기 (VMware Tools 응답 대기)"
  local ip
  ip="$(detect_vm_ip)" || { echo "IP 감지 실패" >&2; return 1; }
  echo "게스트 IP: $ip"
  printf '%s' "$ip" > "$VM_IP_FILE"

  echo "SSH 응답 대기"
  local deadline=$((SECONDS + SSH_WAIT_TIMEOUT))
  until ssh_vm "${VM_USER}@${ip}" 'echo ready' >/dev/null 2>&1; do
    (( SECONDS < deadline )) || { echo "SSH 대기 시간 초과" >&2; return 1; }
    sleep 3
  done
  echo "준비 완료"
}

log "VM 롤백을 비동기로 시작"
rollback_vm \
   > >(stdbuf -oL sed 's/^/[VM] /')      \
  2> >(stdbuf -oL sed 's/^/[VM] /' >&2)  &
ROLLBACK_PID=$!

log "호스트에서 './build -v enterprise' 실행"
BUILD_RC=0
./build -v enterprise \
   > >(stdbuf -oL sed 's/^/[BUILD] /')      \
  2> >(stdbuf -oL sed 's/^/[BUILD] /' >&2)  || BUILD_RC=$?

if (( BUILD_RC != 0 )); then
  fail "빌드 실패 (exit=$BUILD_RC)"
fi
log "빌드 완료"

log "VM 롤백 완료 대기"
ROLLBACK_RC=0
wait "$ROLLBACK_PID" || ROLLBACK_RC=$?
unset ROLLBACK_PID
(( ROLLBACK_RC == 0 )) || fail "VM 롤백 또는 SSH 준비 실패 (exit=$ROLLBACK_RC)"

VM_HOST="$(cat "$VM_IP_FILE")"
[[ -n "$VM_HOST" ]] || fail "감지된 VM IP가 비어 있습니다"
log "VM 접속 주소 확정: ${VM_USER}@${VM_HOST}"

# ───── 2단계: outputs 디렉터리 전체를 VM으로 전송 ─────
[[ -d "$OUTPUT_DIR" ]] || fail "'$OUTPUT_DIR' 디렉터리가 없습니다"

log "원격 스테이징 디렉터리 초기화: ${REMOTE_STAGING}"
ssh_vm "${VM_USER}@${VM_HOST}" \
  "rm -rf -- '${REMOTE_STAGING}' && mkdir -p -- '${REMOTE_STAGING}'"

log "'${OUTPUT_DIR}/' → ${VM_USER}@${VM_HOST}:${REMOTE_STAGING}/ 전송"
# 디렉터리 내용물을 통째로 복사 (마지막 '/.' 가 핵심)
scp_vm "${OUTPUT_DIR}/." "${VM_USER}@${VM_HOST}:${REMOTE_STAGING}/"

# ───── 3단계: VM에서 .deb 일괄 설치 후 재시동 ─────
log "VM에서 .deb 설치 진행"
# sudo도 동일 비밀번호로 사용. 원격에 SUDO_PASS를 환경변수로 안전 전달.
ssh_vm -t "${VM_USER}@${VM_HOST}" \
    "STAGING='${REMOTE_STAGING}' SUDO_PASS='${VM_PASSWORD}' bash -s" <<'REMOTE' \
   > >(stdbuf -oL sed 's/^/[VM] /')      \
  2> >(stdbuf -oL sed 's/^/[VM] /' >&2)
set -Eeuo pipefail

mapfile -t debs < <(find "$STAGING" -type f -name '*.deb' | sort)
if (( ${#debs[@]} == 0 )); then
  echo "설치할 .deb 파일이 없습니다: $STAGING" >&2
  exit 1
fi

echo "발견된 패키지 ${#debs[@]}개:"
printf '  - %s\n' "${debs[@]}"

# sudo에 비밀번호를 stdin으로 주입 (-S), 비대화형 환경 안전화
SUDO=( sudo -S -p '' )
export DEBIAN_FRONTEND=noninteractive

printf '%s\n' "$SUDO_PASS" | "${SUDO[@]}" apt-get update
printf '%s\n' "$SUDO_PASS" | "${SUDO[@]}" apt-get install -y --no-install-recommends "${debs[@]}"

echo "설치 완료. 재시동 예약(2초 후)"
# SSH 세션 종료 후 재시동되도록 백그라운드 + 분리.
# setsid로 컨트롤링 터미널 분리해 SSH가 끊겨도 systemctl reboot가 살아있도록 함.
printf '%s\n' "$SUDO_PASS" | "${SUDO[@]}" -b \
  setsid bash -c 'sleep 2; systemctl reboot' >/dev/null 2>&1 || true
REMOTE

log "재시동 명령 전달 완료. 파이프라인 정상 종료"
