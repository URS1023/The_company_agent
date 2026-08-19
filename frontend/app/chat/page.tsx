"use client";

import { FormEvent, useState } from "react";

type Message = { role: "user" | "assistant"; content: string };

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = input.trim();
    if (!value || running) return;
    setMessages((current) => [...current, { role: "user", content: value }]);
    setInput("");
    setRunning(true);
    window.setTimeout(() => {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "工作台骨架已就绪。下一步会接入真实 Run、知识库和模型 Provider。" }
      ]);
      setRunning(false);
    }, 300);
  }

  return (
    <div className="chat-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><span className="brand-mark">CA</span><span>企业 AI</span></div>
        <button className="new-chat" onClick={() => setMessages([])}>＋ 新建对话</button>
        <nav aria-label="主导航" className="main-nav">
          <a className="active" href="/chat">对话</a>
          <a href="#knowledge">知识库</a>
          <a href="#plugins">插件</a>
          <a href="#files">文件</a>
          <a href="#sources">数据源</a>
        </nav>
        <div className="sidebar-spacer" />
        <div className="workspace-chip"><span className="status-dot" /> 默认工作区</div>
        <a className="sidebar-user" href="/login">管理员 · 设置</a>
      </aside>
      <main className="chat-main">
        <header className="chat-header">
          <div><span className="chat-title">新对话</span><span className="chat-context"> · 默认工作区</span></div>
          <button className="details-button" type="button">执行详情</button>
        </header>
        <section className="message-column" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-mark">CA</div>
              <h1>今天要完成什么工作？</h1>
              <p>上传文件、选择知识库，或直接描述你想完成的业务任务。</p>
              <div className="suggestion-row">
                <button type="button" onClick={() => setInput("根据招标文件生成投标材料")}>根据招标文件生成投标材料</button>
                <button type="button" onClick={() => setInput("分析经营数据并生成汇报")}>分析经营数据并生成汇报</button>
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="message-role">{message.role === "user" ? "你" : "企业 AI"}</div>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </section>
        <form className="composer-wrap" onSubmit={submit}>
          <div className="context-chips"><button type="button">＋ 添加文件</button><button type="button">选择知识库</button><button type="button">使用插件</button></div>
          <div className="composer">
            <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="输入消息…" rows={1} aria-label="消息输入" />
            <button className="send-button" type="submit" disabled={!input.trim() || running} aria-label={running ? "正在处理" : "发送消息"}>{running ? "…" : "↑"}</button>
          </div>
          <p className="composer-hint">AI 可能出错。重要信息请查看来源和执行详情。</p>
        </form>
      </main>
      <aside className="trace-rail" aria-label="证据轨道">
        <p className="rail-kicker">证据轨道</p>
        <div className="rail-line"><span>输入来源</span><i /><span>执行步骤</span><i /><span>输出成果</span></div>
        <p className="rail-note">运行任务后，这里会显示文件、知识、Tool 和 Artifact 的血缘关系。</p>
      </aside>
    </div>
  );
}
