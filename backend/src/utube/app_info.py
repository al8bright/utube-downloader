"""앱마다 다른 값. 공통 파일(api/base.py, core/proc.py)은 이름과 포트를 여기서 읽는다. (docs/STRUCTURE.md)"""

NAME = "utube"  # 패키지·명령 이름. 토큰 헤더는 X-Utube-Token
ENV = "UTUBE"  # 환경 변수 접두사: UTUBE_TOKEN, UTUBE_HOME, 준비 신호 UTUBE_LISTENING
PORT = 8766  # `utube serve` 기본 포트(개발용. 앱은 --port 0으로 빈 포트를 쓴다)
VITE_PORT = 5174  # 화면 개발 서버(pnpm dev)
