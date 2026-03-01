## ===== Cheeeezzk Discord Bot V1.0 =====

쿠키를 입력받아 네이버계정 로그인을 하면 현재 팔로우중인 스트리머의 방송 시작, 방제 및 카테고리 변경, 방송 종료 알림을 보내주는 디스코드 봇입니다.

1. Python 3.10 이상 설치
2. pip install -r requirements.txt
3. .env.example → .env 이름 변경
4. DISCORD_TOKEN 입력
5. config.json.example → config.json 이름 변경
5. python main.py 실행

[스트리밍 알림 BOT](https://streaming-bot.czzk.kr) 및 [푸딩][def]을 다소 참고하였으며,  
문제시 레포지토리 비공개 처리토록 하겠습니다.

명령어:  
/help  
/login <NID_AUT> <NID_SES>  
/logout  
/setchannel  

코드의 대부분은 ChatGPT가 작성했으며, 오류 발생시 ISSUE작성 부탁드립니다.

## ===== 업데이트 로그 =====

V1.1 : /help 및 /logout추가, 방송종료 임베드 추가, 방송 정보 변경에 태그 변경 추가 및 임베드 하나로 묶임, 명령어 설명 개선, 상태 저장 로직 개선  
V1.0 : first commit

## ===== 주의사항 =====

봇 하나당 서버 하나의 단일 서버만을 고려하고 개발되었으며,  
봇 하나에 여러개의 서버의 다중 서버 사용시에 발생되는 일들은 책임지지 않습니다.

봇 추가시 서버에 있는 모든 인원이 명령어를 사용할 수 있는 권한이 생기며,  
이에 대해 발생되는 일들은 책임지지 않습니다.

/login 명령어 사용시에 쿠키값은 config.json에 저장되며,  
config.json 노출시에 발생되는 일들은 책임지지 않습니다.

Cheeeezzk Discord Bot는 치지직 비공식api를 사용하며,  
임의로 CHECK_INTERVAL를 줄여서 발생되는 일들은 책임지지 않습니다.



[def]: https://ddockson.notion.site/60e24ce5dee549faaee5bc7f4084efae