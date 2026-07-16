# 유튜브 다운로드 중단 기능 구현 및 대기열 반복 다운로드 에러 해결 계획

유튜브 뮤직/영상 다운로더(`youtube_down`) 프로그램 가동 시 발생하는 1) 대기열 1개 구동 시 플레이리스트 전체 혹은 후속 미디어가 지속 다운로드되는 중복 루프 에러를 해결하고, 2) 다운로드 실행 중 사용자가 원할 때 즉시 다운로드를 멈출 수 있는 **`다운로드 중단`** 기능을 안전하게 탑재합니다.

---

## 📌 주요 해결 과제 및 요구사항

1. **지속 반복 다운로드 에러 해결 (`noplaylist` 추가)**:
   * 유튜브 단일 주소를 추가하거나 검색 후 다운로드할 때, 해당 영상 주소 뒤에 플레이리스트 매개변수(`&list=...`) 등이 붙어 있으면 `yt-dlp`가 관련 플레이리스트 전원을 연속 인코딩해 버리는 구조적 문제가 있습니다.
   * `yt-dlp` 호출 사양의 `ydl_opts`에 **`noplaylist: True`** 필드를 강제 부여하여 단일 타겟 비디오 이외의 중복 로드를 차단합니다. (검색 flat 추출 분석 스레드 및 실제 파일 다운로드 스레드 모두 연동)

2. **다운로드 중단 기능 구현**:
   * 대기열 제어부 하단 버튼 바(`btn_row`)에 **`다운로드 중단`** 버튼을 신설합니다. (초기 상태: 비활성 `disabled` ➡️ 다운로드 시작 시: 경고형 붉은 톤 활성화)
   * 버튼 클릭 시 `stop_requested` 플래그를 `True`로 활성화하고, 현재 진행 중인 백그라운드 인코딩 작업을 끊기 위해 `yt-dlp` `progress_hook`에서 정지 예외(`aborted by user`)를 던지도록 설계합니다.
   * 순차 대기열 처리 루프(`batch_download_loop`)도 각 영상 다운로드 개시 직전에 `stop_requested` 플래그를 감지하여 즉시 루프를 탈출(`break`)하도록 분기합니다.
   * 중단이 끝나면 전체 상태 바와 UI 위젯들을 리셋 및 일반 사용 상태(`normal`)로 깔끔하게 원상 복귀합니다.

---

## 🛠️ Proposed Changes

### [youtube_down Component](file:///c:/Personal/youtube_down)

#### [MODIFY] [gui_app.py](file:///c:/Personal/youtube_down/gui_app.py)

1. **`__init__`**:
   * 중단 제어 플래그 변수 `self.stop_requested = False`를 초기 상태 변수 목록에 추가합니다.
2. **`create_widgets`**:
   * 대기열의 `btn_row` 버튼 바 내부 pack 구조를 3분할 배치로 개편하여 **`다운로드 중단`** 버튼을 추가 연동합니다.
3. **`start_selected_download`**:
   * 다운로드 구동 직전 `self.stop_requested = False`로 리셋하고, '다운로드 중단' 버튼을 `normal` 상태 및 눈에 띄는 빨간색 톤으로 전환하여 즉시 정지가 가능하게 연동합니다.
4. **`request_stop_download`**:
   * 중단 버튼 클릭 시 호출될 콜백 함수를 작성하여 `stop_requested = True` 처리 및 상태 라벨 전환을 주도합니다.
5. **`batch_download_loop`**:
   * 대기열 순회 도중 `self.stop_requested`가 감지되면 즉각 `break`하여 후속 다운로드를 스킵하게 조치합니다.
6. **`download_single`**:
   * `progress_hook` 내에 중단 감시 분기(`raise Exception("Download aborted by user")`)를 구현하여 실행 중인 `yt-dlp` 네이티브 전송/다운로드 파이프라인을 강제 정지 처리합니다.
   * `ydl_opts` 설정 항목에 `'noplaylist': True`를 삽입하여 불필요한 연속 플레이리스트 변환 문제를 원천 제거합니다.
7. **`analyze_direct_url_thread`**:
   * 직접 링크 추가 시에도 플레이리스트 전량이 탐색되는 것을 막기 위해 `ydl_opts`에 `'noplaylist': True`를 반영합니다.
8. **`on_batch_download_complete`**:
   * 중단 완료 여부 분기 조건문을 도입하여, 유저가 중단을 눌러 끝났을 때와 대기열 다운로드가 정상 완료되었을 때의 UI 가이드 문구와 버튼 활성화 처리를 독립화합니다.

---

## 🎯 Verification Plan

### Automated Tests
* `python -m py_compile gui_app.py`를 호출하여 문법 오타 여부 검증.

### Manual Verification
1. **중단 버튼 정상 연동 확인**: 다운로드가 실행되지 않았을 때 '다운로드 중단' 버튼이 비활성화되는지, 다운로드를 켜면 붉은색 활성 톤으로 전환되는지 확인합니다.
2. **단일 비디오 다운로드 검증**: 플레이리스트 태그가 포함된 유튜브 곡 주소를 대기열에 1개 올린 뒤 다운로드를 수행하여, 예전처럼 계속 이어서 받지 않고 정확히 1개의 음성/영상 파일만 정상 저장되는지 확인합니다.
3. **다운로드 도중 중단 강제 구동**: 
   * 다량의 음악 다운로드를 건 후 변환 도중에 '다운로드 중단' 버튼을 직접 마우스 클릭합니다.
   * 즉시 현재 곡 다운로드가 끊기고, 대기열 루프가 멈추며 대기열 상태바가 `다운로드 중단됨!`으로 갱신되고 모든 버튼이 활성화 상태로 돌아오는지 검토합니다.
4. **실행 파일 빌드**: `build_exe.bat`를 돌려 배포판 `YoutubeDownloader.exe`로 안전하게 갱신 빌드되는지 검사합니다.
