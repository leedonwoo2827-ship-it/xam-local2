"""사내망 공유 — **보기 전용** 게이트.

왜 이 파일이 있는가
────────────────────────────────────────────────────────────────────────────
`run.bat` 은 `--host 127.0.0.1` 로 띄운다. 일부러다 — 이 콘솔은 BOOK 트리
(문제은행 원본)를 **쓴다**. 인증이 없으므로 사내망에 그대로 열면 그 망에 있는
누구나 720문항을 고치거나 지울 수 있다.

그런데 "UI/UX 를 동료에게 보여주고 싶다" 는 요구는 정당하고, 그건 **읽기만**
있으면 된다. 그래서 규칙을 하나로 좁혔다:

    루프백(127.0.0.1 · ::1)     → 전부 허용. 내 화면은 지금과 똑같다.
    그 밖(사내망에서 들어온 것)  → **GET / HEAD 만.** 나머지는 403.

왜 메서드로 갈랐는가 — 엔드포인트를 하나씩 분류하면 새 라우트가 생길 때마다
빠뜨린다. 그 실수는 "조용히 쓰기가 열린다" 는 방향이라 최악이다. 메서드는
FastAPI 데코레이터가 이미 정확히 들고 있어서 빠뜨릴 자리가 없다.

실측으로 확인한 것(2026-08-04): GET 45 · POST 27 · PUT 4 이고 POST/PUT 은 전부
실제 쓰기다(빌드·렌더·저장·붙여넣기·부분임포트). 문항 미리보기와 수식 렌더는
브라우저가 하므로 보기 전용에서도 그대로 나온다 — 화면이 깨지지 않는다.

★ 이건 보안 경계가 아니라 **사고 방지선**이다. 사내망을 신뢰한다는 전제이고,
  토큰도 암호도 없다. 인터넷에 노출하는 데 쓰면 안 된다.
"""

from __future__ import annotations

import ipaddress
import socket

# 이 메서드만 사내망 클라이언트에게 허용한다. OPTIONS 는 넣지 않는다 —
# 같은 출처에서만 부르므로 프리플라이트가 필요 없고, 넣으면 규칙만 넓어진다.
READ_METHODS = frozenset({"GET", "HEAD"})

# ★ v2 — 보기 전용의 **유일한 예외**: 듣기 검수 판정 한 줄(덧붙이기만 하는 기록).
#   여러 사람이 각자 자리에서 듣고 OK·고칠 곳을 누르는 것이 그 기능의 전부다.
#   원고를 바꾸는 것(지적 반영·장 편집)은 여기 없다 — 운영자 PC 에서만 된다.
#   경로를 정규식 하나로 못박는다. 접두 비교로 넓히면 같은 접두의 쓰기가 같이 열린다.
import re as _re
_LAN_WRITABLE = _re.compile(r"^/api/lecture/(summary|full)/[A-Za-z0-9_-]{1,40}/review$")


def lan_writable(method: str, path: str) -> bool:
    return method == "POST" and bool(_LAN_WRITABLE.match(path or ""))


def is_local(host: str | None) -> bool:
    """루프백에서 온 요청인가.

    ★ 문자열 비교로 하지 않는다. `::ffff:127.0.0.1`(IPv4-mapped IPv6)도 루프백이고,
      `127.0.0.1` 만 비교하면 그 형태로 들어온 **내 요청이 보기 전용으로 떨어진다**.
      ipaddress 가 두 형태를 다 알아본다.

    host 가 None 이면(테스트 클라이언트·유닉스 소켓) 로컬로 본다 — 사내망을 거쳐
    들어온 요청은 항상 주소를 갖는다.
    """
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) 는 is_loopback 이 False 다 — 벗겨서 다시 본다.
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(mapped and mapped.is_loopback)


def lan_ips() -> list[str]:
    """이 PC 가 사내망에서 가진 IPv4 주소들.

    두 방법을 합친다. 어느 하나만으로는 자주 빈손이 된다:
      · UDP 연결 트릭 — 실제로 바깥으로 나가는 인터페이스를 고른다. 패킷은 보내지
        않는다(connect 만 하면 커널이 경로를 정한다). 기본 경로가 없으면 실패한다.
      · getaddrinfo(hostname) — 여러 NIC(유선+무선+VPN)를 다 준다. 다만 hosts 파일
        설정에 따라 127.0.0.1 만 줄 때가 있다.

    루프백·링크로컬(169.254.x, APIPA)은 뺀다 — 동료가 그 주소로는 못 들어온다.
    """
    found: list[str] = []

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))          # 패킷은 나가지 않는다
        found.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass

    out: list[str] = []
    for a in found:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local:
            continue
        if a not in out:
            out.append(a)
    return out


def _main() -> None:
    """`lan.bat` 이 부른다. 배치에서 IP 를 캐내는 것보다 여기가 정확하다."""
    from core.constants import PORT

    ips = lan_ips()
    if not ips:
        print("  [WARN] LAN IPv4 address not found.")
        print("         Check your network, then find it with:  ipconfig")
        return
    for a in ips:
        print(f"    http://{a}:{PORT}/")


if __name__ == "__main__":
    _main()
