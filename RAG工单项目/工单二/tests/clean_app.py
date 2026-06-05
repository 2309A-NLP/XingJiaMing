with open(r'E:\桌面\项目文件\RAG工单项目\工单二\frontend\src\App.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 删除语言状态
content = content.replace('const [language, setLanguage] = useState("zh")\n', '')

# 删除 InputBox 的 language 和 onLanguageChange props
content = content.replace('''          disabled={loading || parsing || !backendOk || !backendReady}
          language={language}
          onLanguageChange={setLanguage}''', 'disabled={loading || parsing || !backendOk || !backendReady}')

# 删除 ChatArea 的 language prop
content = content.replace('''            language={language}
          />''', '''          />''')

# 修改 queryStream 调用，删除 language 参数
content = content.replace('await queryStream(text, 5, language,', 'await queryStream(text, 5, "zh",')

with open(r'E:\桌面\项目文件\RAG工单项目\工单二\frontend\src\App.tsx', 'w', encoding='utf-8') as f:
    f.write(content)

print('已清理 App.tsx')
