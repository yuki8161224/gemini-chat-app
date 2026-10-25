import io
import pandas as pd
import streamlit as st
import google.generativeai as genai
from datetime import datetime

# --- ページ基本設定 ---
st.set_page_config(page_title="対話実験システム", layout="centered")

# --- Gemini API 設定 ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("APIキーが設定されていません。.streamlit/secrets.toml を確認してください。")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# 実験用共通システムプロンプト
SYSTEM_INSTRUCTION = """
あなたはアイドルの顔の好みに関するインタビューを行うAIです。

あなたの目的は、対話を通じて被験者がどのような顔を好むのかを自然に聞き出すことです。
あなたは被験者の評価データや好きなアイドル画像などの情報は一切知りません。
会話の中で得られた情報だけをもとに質問してください。

## 会話方針
・自然な会話を心掛ける
・一度にする質問は「1つだけ」にする
・相手の回答に応じて次の質問を柔軟に考える
・回答を丁寧に深掘りする
・決めつけない
・特定の好みに誘導しない
・心理テストのような断定をしない
・適度に相づちを入れ、相手が話しやすい温かい雰囲気を作る

## 聞き出したい内容
以下の内容を一度にすべて聞くのではなく、会話の流れの中で自然に収集してください。
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

## 深掘りの例
回答に対して、以下のように詳しく情報を引き出してください。
・「どうしてそう思いますか？」
・「具体的にはどんなところですか？」
・「例えば誰が近いですか？」
・「もし○○だったら印象は変わりますか？」

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

## 注意事項
・同じ質問を繰り返さないこと
・既に得られた情報を踏まえて次の質問を組み立てること
・質問攻めにせず、適度に共感や相づちを挟むこと
・20～30往復程度の会話で十分な情報を得ることを目標とすること
・インタビューが一通り完了したと判断した場合は、被験者へ感謝のお礼を伝えて対話を締めくくってください
"""

# モデルの初期化
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

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

# 1. 被験者IDの入力画面
if not st.session_state.user_id:
    st.info("実験を開始する前に、指定された被験者IDを入力してください。")
    with st.form("id_form"):
        user_id_input = st.text_input("被験者ID (例: sub_01):")
        submitted = st.form_submit_button("実験を開始")
        if submitted:
            if user_id_input.strip():
                st.session_state.user_id = user_id_input.strip()
                
                # --- AIの最初の挨拶・質問を生成 ---
                try:
                    # 初期トリガーメッセージ（裏側からプロンプトを叩く）
                    initial_prompt = "インタビューを開始してください。被験者への簡単な挨拶と、最初の質問（好きなアイドルや芸能人についてなど）を1つだけ投げかけてください。"
                    first_res = st.session_state.chat_session.send_message(initial_prompt)
                    
                    st.session_state.messages.append({
                        "user_id": st.session_state.user_id,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "turn": 1,
                        "role": "assistant",
                        "content": first_res.text
                    })
                except Exception as e:
                    st.error(f"初期メッセージ生成エラー: {e}")
                
                st.rerun()
            else:
                st.warning("IDを入力してください。")
    st.stop()

# --- サイドバー表示 ---
st.sidebar.markdown(f"**参加者ID:** `{st.session_state.user_id}`")
st.sidebar.markdown("---")

# 2. 実験終了 ＆ ダウンロード処理
if st.session_state.is_finished:
    st.success("🎉 インタビューが終了しました！ご協力ありがとうございました。")
    st.warning("⚠️ 以下のボタンから必ず会話ログ（CSV）をダウンロードし、担当者に提出してください。")
    
    # CSV生成 (Excel対応のutf-8-sig)
    df_logs = pd.DataFrame(st.session_state.messages)
    csv_buffer = io.BytesIO()
    df_logs.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    
    file_name = f"log_{st.session_state.user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    st.download_button(
        label="📥 会話ログ(CSV)をダウンロード",
        data=csv_buffer.getvalue(),
        file_name=file_name,
        mime="text/csv",
        type="primary",
        use_container_width=True
    )
    st.stop()

# 進行中のサイドバー：終了ボタン
if len(st.session_state.messages) > 1:
    st.sidebar.markdown("インタビューが終わったら下のボタンを押してください。")
    if st.sidebar.button("対話を終了してCSVを出力", type="primary"):
        st.session_state.is_finished = True
        st.rerun()

# 3. チャット履歴の描画
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# 4. ユーザーの入力フォーム
if prompt := st.chat_input("メッセージを入力してEnterを押してください..."):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_turn = (len(st.session_state.messages) // 2) + 1
    
    # ユーザー発話記録
    st.session_state.messages.append({
        "user_id": st.session_state.user_id,
        "timestamp": timestamp,
        "turn": current_turn,
        "role": "user",
        "content": prompt
    })
    with st.chat_message("user"):
        st.write(prompt)

    # Gemini応答記録
    try:
        response = st.session_state.chat_session.send_message(prompt)
        res_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.session_state.messages.append({
            "user_id": st.session_state.user_id,
            "timestamp": res_timestamp,
            "turn": current_turn,
            "role": "assistant",
            "content": response.text
        })
        with st.chat_message("assistant"):
            st.write(response.text)
            
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")