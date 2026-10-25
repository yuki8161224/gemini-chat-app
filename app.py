import io
import pandas as pd
import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- ページ基本設定 ---
st.set_page_config(page_title="対話実験システム", layout="centered")

# --- 設定値の検証 ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
SPREADSHEET_ID = st.secrets.get("SPREADSHEET_ID", "")

if not GEMINI_API_KEY or not SPREADSHEET_ID:
    st.error("設定情報（APIキーまたはスプレッドシートID）が不足しています。.streamlit/secrets.toml を確認してください。")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# 実験用システムプロンプト（省略せず全文配置）
SYSTEM_INSTRUCTION = """
あなたはアイドルの顔の好みに関するインタビューを行うAIです。

あなたの目的は、対話を通じて被験者がどのような顔を好むのかを自然に聞き出すことです。

あなたは被験者の評価データや好きなアイドル画像などの情報は一切知りません。
会話の中で得られた情報だけをもとに質問してください。

## 会話方針

・自然な会話を心掛ける
・一度に質問は1つだけ
・回答に応じて次の質問を考える
・回答を深掘りする
・決めつけない
・誘導しない
・心理テストのような断定をしない
・相手が話しやすい雰囲気を作る

## 聞き出したい内容

以下の内容を会話の中で自然に収集してください。

・好きなアイドルや芸能人
・好きな理由
・顔のどこを見ることが多いか
・目、鼻、口、輪郭、髪型などで重視する点
・かわいい、かっこいいと感じる特徴
・優しそう、大人っぽい、幼いなど好きな印象
・笑顔や表情の影響
・好きではない顔の特徴
・第一印象で判断するか
・顔以外に影響する要素があるか
・自分でも説明しにくい好みがあるか

## 深掘り

回答に対して

「どうしてそう思いますか？」

「具体的にはどんなところですか？」

「例えば誰が近いですか？」

「もし○○だったら印象は変わりますか？」

など、より詳しく情報を引き出してください。

## 質問例

・好きなアイドルはいますか？
・その人のどこが好きですか？
・顔で一番最初に目がいくのはどこですか？
・目元はどんなタイプが好きですか？
・輪郭は丸顔と面長ならどちらが好きですか？
・笑顔は重要ですか？
・かわいい系とか美人系ならどちらが好みですか？
・逆にあまり好みではない顔はありますか？
・初めて見た瞬間に好きになることはありますか？

## 会話ログの出力

インタビューが終了したら、会話内容をCSV形式で出力してください。

CSVは以下の列を使用してください。

turn,speaker,text

- turn：会話番号（1から順番）
- speaker：AI または Participant
- text：発話内容

出力例

turn,speaker,text
1,AI,"本日はご協力ありがとうございます。好きなアイドルはいますか？"
2,Participant,"○○さんが好きです。"
3,AI,"その方のどんなところが好きですか？"
4,Participant,"目が優しくて笑顔がかわいいところです。"

会話終了後は、CSVのみを出力してください。
余計な説明やMarkdown、コードブロックは不要です。

## 注意

・同じ質問を繰り返さない
・既に得られた情報を踏まえて質問する
・質問ばかり続けず適度に相づちを入れる
・20～30問程度の会話で十分な情報を得ることを目標とする

最後は被験者へのお礼で終了してください。
"""

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# 応答テキストの安全な抽出関数
def extract_text(response):
    try:
        if response.text:
            return response.text
    except Exception:
        pass
    if hasattr(response, "candidates") and response.candidates:
        cand = response.candidates[0]
        if hasattr(cand, "content") and hasattr(cand.content, "parts"):
            text_parts = [p.text for p in cand.content.parts if hasattr(p, "text")]
            if text_parts:
                return "".join(text_parts)
    return "うまく聞き取れませんでした。もう一度入力していただけますか？"

# --- Googleスプレッドシートへの一括書き込み関数 ---
def save_logs_to_spreadsheet(user_id, messages):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        worksheet = sheet.worksheet(user_id)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=user_id, rows=100, cols=10)
    
    header = ["turn", "speaker", "text", "timestamp"]
    rows = [header]
    for msg in messages:
        speaker_label = "AI" if msg["role"] == "assistant" else "Participant"
        rows.append([
            msg["turn"],
            speaker_label,
            msg["content"],
            msg["timestamp"]
        ])
    
    worksheet.update(rows)
# --- セッション初期化 ---
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])
if "is_finished" not in st.session_state:
    st.session_state.is_finished = False

st.title("アイドルの好みに関する対話実験")

# 1. 被験者ID入力
if not st.session_state.user_id:
    st.info("実験を開始する前に、指定された被験者IDを入力してください。")
    with st.form("id_form"):
        user_id_input = st.text_input("被験者ID (例: sub_01):")
        submitted = st.form_submit_button("実験を開始")
        if submitted:
            if user_id_input.strip():
                st.session_state.user_id = user_id_input.strip()
                
                # --- Geminiから最初の1通目を自動生成させて開始 ---
                with st.spinner("対話を準備しています..."):
                    try:
                        # 最初の発話を促すトリガー送信
                        start_prompt = "インタビューを開始してください。挨拶と最初の質問を1つだけ投げかけてください。"
                        first_res = st.session_state.chat_session.send_message(start_prompt)
                        first_text = extract_text(first_res)
                        
                        st.session_state.messages.append({
                            "user_id": st.session_state.user_id,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "turn": 1,
                            "role": "assistant",
                            "content": first_text
                        })
                    except Exception as e:
                        # フォールバック用の初期挨拶
                        st.session_state.messages.append({
                            "user_id": st.session_state.user_id,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "turn": 1,
                            "role": "assistant",
                            "content": "本日はインタビューにご協力いただきありがとうございます。普段「好きだな」「魅力的だな」と思うアイドルや芸能人はいらっしゃいますか？"
                        })
                st.rerun()
            else:
                st.warning("IDを入力してください。")
    st.stop()

# --- サイドバー表示 ---
st.sidebar.markdown(f"**参加者ID:** `{st.session_state.user_id}`")
st.sidebar.markdown("---")

# 2. 実験終了 ＆ スプレッドシート送信処理
if st.session_state.is_finished:
    st.success("🎉 対話実験が終了しました！ログはサーバーに正常に保存されました。")
    st.info("ご協力ありがとうございました。ブラウザを閉じて終了してください。")
    
    # バックアップ用の手動CSVダウンロード
    df_logs = pd.DataFrame(st.session_state.messages)
    csv_buffer = io.BytesIO()
    df_logs.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        label="（任意）会話ログの予備控えをダウンロード",
        data=csv_buffer.getvalue(),
        file_name=f"log_{st.session_state.user_id}.csv",
        mime="text/csv"
    )
    st.stop()

# 終了ボタン
if len(st.session_state.messages) > 1:
    st.sidebar.markdown("対話が完了したら下のボタンを押してください。")
    if st.sidebar.button("対話を終了して記録を保存", type="primary"):
        with st.spinner("会話ログを保存しています..."):
            try:
                save_logs_to_spreadsheet(st.session_state.user_id, st.session_state.messages)
                st.session_state.is_finished = True
                st.rerun()
            except Exception as e:
                st.error(f"スプレッドシートへの保存に失敗しました: {e}")

# 3. チャット描画
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# 4. 発話受付
if prompt := st.chat_input("メッセージを入力してEnterを押してください..."):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_turn = (len(st.session_state.messages) // 2) + 1
    
    st.session_state.messages.append({
        "user_id": st.session_state.user_id,
        "timestamp": timestamp,
        "turn": current_turn,
        "role": "user",
        "content": prompt
    })
    with st.chat_message("user"):
        st.write(prompt)

    try:
        response = st.session_state.chat_session.send_message(prompt)
        res_text = extract_text(response)
        res_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.session_state.messages.append({
            "user_id": st.session_state.user_id,
            "timestamp": res_timestamp,
            "turn": current_turn,
            "role": "assistant",
            "content": res_text
        })
        with st.chat_message("assistant"):
            st.write(res_text)
            
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")