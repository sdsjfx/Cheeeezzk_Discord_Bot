## ===== 주의사항 =====

봇 하나당 서버 하나의 단일 서버만을 고려하고 개발되었으며,  
봇 하나에 여러개의 서버의 다중 서버 사용시에 발생하는 일들은 책임지지 않습니다.

## ===== Cheeeezzk Discord Bot V1.0 =====

네이버계정 로그인을 하면 팔로우중인 스트리머의 방송 시작, 방제 및 카테고리 변경, 방송 종료 알림을 보내줍니다.

1. Python 3.10 이상 설치
2. pip install -r requirements.txt
3. .env.example → .env 이름 변경
4. DISCORD_TOKEN 입력
5. config.json.example → config.json 이름 변경
5. python main.py 실행

[스트리밍 알림 BOT](https://streaming-bot.czzk.kr)을 다소 참고하였으며,  
문제시 레포지토리 비공개 처리토록 하겠습니다.

명령어:  
/login <NID_AUT> <NID_SES>  
/setchannel  

코드의 대부분은 ChatGPT가 작성했으며, 오류 발생시 ISSUE작성 부탁드립니다.