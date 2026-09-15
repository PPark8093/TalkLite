# TalkLite
Made With ViveCoding

## Usage
1. Extract ```TalkLite.zip```
2. run ```build_windows.bat```
3. Open ```dist``` folder and run ```TalkLite.exe```
### 1. 친구 A — 전화 거는 사람 (서버)
1. `TalkLite.exe` 실행
2. `"내가 전화 걸기 (서버)"` 클릭
3. 통화 대기 시작
4. 친구에게 본인의 IP 주소 전달

### 2. 친구 B — 받는 사람 (클라이언트)
1. `TalkLite.exe` 실행
2. `"친구에게 받기"` 클릭
3. A의 IP 주소 입력
4. 친구에게 연결 및 통화 시작

---

### 네트워크 연결 가이드

#### 동일 네트워크 (같은 공유기 / Wi-Fi)
* **A의 PC IP**: `192.168.0.15` (Example)
* **B의 접속 방법**: `192.168.0.15` 입력 $\rightarrow$ 연결 $\rightarrow$ 음성통화 시작

#### 외부 네트워크 (인터넷을 통해 서로 다른 장소에서 연결할 경우)
> **포트포워딩 설정 필요**  
> 외부 인터넷을 통해 통화하려면 A의 공유기 설정에서 **TCP 39876** 포트를 **A의 PC IP**로 포트포워딩해야 합니다.

---

## It runs with just the .exe file—no other files required.
