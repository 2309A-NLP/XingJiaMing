#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融数字人RAG问答系统 - 主程序
用户输入问题 → RAG检索 → TTS语音合成 → SadTalker+MuseTalk视频生成
"""

import os
import re
import time
import requests
import subprocess
import gradio as gr

# ===== 配置 =====
RAG_API_URL = 'https://herself-ferment-accustom.ngrok-free.dev'
HEADERS = {'ngrok-skip-browser-warning': 'true'}
SOURCE_IMAGE = './inputs/金融男.png'
SOURCE_VIDEO = './inputs/金融男_source.mp4'
TTS_VOICE = 'zh-CN-YunyangNeural'  # 男声

# ===== 初始化模块 =====
print('加载模块...')
from TTS import EdgeTTS
edgetts = EdgeTTS()

from TFG import SadTalker, MuseTalk_RealTime

# 加载SadTalker
sadtalker = SadTalker(lazy_load=True)

# 加载MuseTalk
musetalker = MuseTalk_RealTime()
musetalker.init_model()

# 生成源视频（如果不存在）
if not os.path.exists(SOURCE_VIDEO):
    print('生成源视频...')
    subprocess.run([
        'ffmpeg', '-y', '-loop', '1', '-i', SOURCE_IMAGE,
        '-c:v', 'libx264', '-t', '5', '-pix_fmt', 'yuv420p',
        '-vf', 'scale=512:512', SOURCE_VIDEO
    ], capture_output=True)

# 准备MuseTalk素材
print('准备MuseTalk素材...')
musetalker.prepare_material(SOURCE_VIDEO, bbox_shift=0)
print('模块加载完成！')

def clean_text_for_tts(text):
    """
    清理文本中的Markdown符号，让TTS读得更自然
    """
    text = re.sub(r'\*+', '', text)        # 去掉*
    text = re.sub(r'#+\s*', '', text)      # 去掉#
    text = re.sub(r'\|', '，', text)        # 表格|转逗号
    text = re.sub(r'-{2,}', '', text)       # 去掉--
    text = re.sub(r'\n+', '。', text)       # 换行转句号
    text = re.sub(r'。{2,}', '。', text)    # 去掉重复句号
    text = re.sub(r'，{2,}', '，', text)    # 去掉重复逗号
    text = text.strip()
    if not text.endswith(('。', '！', '？', '.', '!', '?')):
        text += '。'
    return text

def query_rag(question):
    """调用RAG API获取回答"""
    try:
        r = requests.post(
            f'{RAG_API_URL}/api/query',
            json={'question': question, 'strategy': 'hybrid'},
            headers=HEADERS,
            timeout=30
        )
        return r.json().get('answer', 'RAG未返回有效回答。')
    except Exception as e:
        return f'RAG出错: {str(e)}'

def rag_digital_human(question):
    """
    完整流程：RAG问答 → TTS → SadTalker → MuseTalk
    """
    if not question or question.strip() == '':
        return '', [], None
    
    t0 = time.time()
    
    # Step 1: RAG检索
    print(f'[1] RAG: {question}')
    answer = query_rag(question)
    clean = clean_text_for_tts(answer)
    print(f'[1] Done {time.time()-t0:.1f}s')
    
    # Step 2: TTS语音合成
    print('[2] TTS...')
    t1 = time.time()
    audio_path = 'answer.wav'
    edgetts.predict(clean, TTS_VOICE, 0, 100, 0, audio_path, 'answer.vtt')
    print(f'[2] Done {time.time()-t1:.1f}s')
    
    # Step 3: SadTalker生成基础视频
    print('[3] SadTalker...')
    t2 = time.time()
    sadtalker_video = sadtalker.test2(
        SOURCE_IMAGE, audio_path,
        preprocess='crop', still_mode=False, use_enhancer=False,
        batch_size=2, size=256, pose_style=0,
        facerender='facevid2vid', exp_scale=1.0,
        use_ref_video=False, ref_info='pose',
        use_idle_mode=False, length_of_audio=0, use_blink=True, fps=20
    )
    print(f'[3] Done {time.time()-t2:.1f}s')
    
    # Step 4: MuseTalk优化口型
    print('[4] MuseTalk...')
    t3 = time.time()
    video = musetalker.inference_noprepare(
        audio_path, sadtalker_video,
        bbox_shift=0, batch_size=4, fps=25
    )
    print(f'[4] Done {time.time()-t3:.1f}s')
    
    total = time.time() - t0
    print(f'===== Total: {total:.1f}s =====')
    
    return '', [(question, answer)], video

# ===== Gradio界面 =====
with gr.Blocks(title='金融数字人RAG问答') as demo:
    gr.Markdown('# 🏦 金融数字人 RAG 问答系统')
    gr.Markdown('输入金融问题，数字人基于知识库回答并生成说话视频。')
    
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=400, show_copy_button=True, label='对话历史')
            msg = gr.Textbox(
                label='输入金融问题',
                placeholder='例如：这两家公司的主要业务是什么？',
                lines=2
            )
            with gr.Row():
                submit_btn = gr.Button('🚀 提问', variant='primary')
                clear_btn = gr.Button('🧹 清除历史')
        
        with gr.Column(scale=1):
            video_output = gr.Video(label='数字人视频', height=400)
            gr.Image(value=SOURCE_IMAGE, label='数字人形象', height=200)
    
    # 绑定事件
    submit_btn.click(
        fn=rag_digital_human,
        inputs=[msg],
        outputs=[msg, chatbot, video_output]
    )
    msg.submit(
        fn=rag_digital_human,
        inputs=[msg],
        outputs=[msg, chatbot, video_output]
    )
    clear_btn.click(
        fn=lambda: ('', [], None),
        outputs=[msg, chatbot, video_output]
    )

# 启动服务
demo.launch(server_name='0.0.0.0', server_port=6006)
