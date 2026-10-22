# 스텔라봇 stella-bot

Discord 채널 하나에서 한국어와 일본어 사용자가 서로 대화할 수 있게 메시지를 실시간으로 번역하는 봇입니다.\
번역문은 원 작성자의 닉네임과 아바타로 표시되고, 답장 관계도 번역문에 그대로 반영됩니다.\
보낸 지 90일이 지나지 않은 메시지는 수정과 삭제도 번역문에 반영됩니다.

## 실행 방법

1. `.env.example`을 `.env`로 복사하고 값을 채웁니다.
2. 의존성 설치: `pip install -r requirements.txt`
3. Discord Developer Portal의 Bot 설정에서 Message Content Intent를 켭니다.
4. 실행: `python main.py`

봇에게 대상 채널의 메시지 보기, 메시지 기록 보기, 웹훅 관리, 반응 추가 권한이 필요합니다.\
새 메시지 번역에 실패하면 원문에 ⚠️ 반응을 답니다.

다른 봇이 보낸 메시지는 기본으로 건너뜁니다.\
봇 메시지도 번역하려면 `.env`에 `ALLOW_BOT_MESSAGES=1`을 넣습니다.

## 테스트

```
pytest
```
