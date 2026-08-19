"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiJson, apiUploadMany } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string };
type RunEvent = { event?: string; payload?: { text?: string; error_summary?: string; error_code?: string; tool?: string; name?: string; step_id?: string; artifact_id?: string }; error?: string };
type Plugin = { id: string; name: string; published_version_id: string | null };
type KnowledgeBase = { id: string; name: string; status: string };
type DataSource = { id: string; name: string; provider: string; status: string };
type SelectedFile = { id: string; name: string; size: number };

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [running, setRunning] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [selectedPluginId, setSelectedPluginId] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [selectedDataSourceId, setSelectedDataSourceId] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [activities, setActivities] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void apiJson<Plugin[]>("/api/v1/plugins").then(setPlugins).catch(() => setPlugins([]));
    void apiJson<KnowledgeBase[]>("/api/v1/knowledge-bases").then(setKnowledgeBases).catch(() => setKnowledgeBases([]));
    void apiJson<DataSource[]>("/api/v1/data-sources").then(setDataSources).catch(() => setDataSources([]));
  }, []);

  async function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    try {
      setError("");
      const uploaded = await apiUploadMany<SelectedFile[]>("/api/v1/files/batch", files);
      setSelectedFiles((current) => [...current, ...uploaded]);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "文件上传失败");
    } finally {
      event.target.value = "";
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = input.trim();
    if (!value || running) return;
    setMessages((current) => [...current, { role: "user", content: value }]);
    setInput("");
    setRunning(true);
    setError("");
    setActivities([]);
    try {
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversationResponse = await fetch("/api/v1/conversations", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "新对话" })
        });
        if (!conversationResponse.ok) throw new Error("创建对话失败，请先登录工作区");
        const conversation = await conversationResponse.json();
        activeConversationId = conversation.id;
        setConversationId(activeConversationId);
      }
      const runResponse = await fetch(`/api/v1/runs/conversations/${activeConversationId}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: value,
          plugin_version_id: selectedPluginId || undefined,
          file_ids: selectedFiles.map((file) => file.id),
          knowledge_base_ids: selectedKnowledgeBaseId ? [selectedKnowledgeBaseId] : [],
          data_source_ids: selectedDataSourceId ? [selectedDataSourceId] : []
        })
      });
      if (!runResponse.ok) throw new Error("Run 创建失败，请检查登录状态和服务状态");
      const run = await runResponse.json();
      setLastRunId(run.id);
      const source = new EventSource(`/api/v1/runs/${run.id}/events`);
      let assistantStarted = false;
      const appendAssistant = (text: string) => {
        if (!text) return;
        setMessages((current) => {
          if (!assistantStarted) {
            assistantStarted = true;
            return [...current, { role: "assistant", content: text }];
          }
          const next = [...current];
          const last = next[next.length - 1];
          if (last?.role === "assistant") next[next.length - 1] = { ...last, content: last.content + text };
          return next;
        });
      };
      const handleEvent = (event: MessageEvent<string>) => {
        const data = JSON.parse(event.data) as RunEvent;
        if (data.event === "message.delta") appendAssistant(data.payload?.text ?? "");
        if (data.event === "run.started") setActivities((current) => [...current, "任务已开始"]);
        if (data.event === "step.started") setActivities((current) => [...current, `开始步骤：${data.payload?.name ?? "未命名"}`]);
        if (data.event === "tool.started") setActivities((current) => [...current, `调用工具：${data.payload?.tool ?? "未知工具"}`]);
        if (data.event === "tool.completed") setActivities((current) => [...current, `工具完成：${data.payload?.tool ?? "未知工具"}`]);
        if (data.event === "artifact.created") setActivities((current) => [...current, `生成 Artifact：${data.payload?.artifact_id ?? ""}`]);
        if (data.event === "run.failed") {
          source.close();
          setError(data.payload?.error_summary ?? data.error ?? "Run 执行失败");
          setRunning(false);
        }
        if (data.event === "run.completed") {
          setActivities((current) => [...current, "任务已完成"]);
          source.close();
          setRunning(false);
        }
      };
      source.addEventListener("message.delta", handleEvent);
      source.addEventListener("run.failed", handleEvent);
      source.addEventListener("run.completed", handleEvent);
      source.onerror = () => {
        source.close();
        setError("事件连接中断；请稍后从 Run Trace 查看后台状态");
        setRunning(false);
      };
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "发送失败");
      setRunning(false);
    }
  }

  return (
    <div className="chat-shell">
      <aside className={`sidebar${navOpen ? " mobile-open" : ""}`}>
        <div className="brand-lockup"><span className="brand-mark">CA</span><span>企业 AI</span></div>
        <button className="new-chat" onClick={() => setMessages([])}>＋ 新建对话</button>
        <nav aria-label="主导航" className="main-nav">
          <a className="active" href="/chat" onClick={() => setNavOpen(false)}>对话</a>
          <a href="/knowledge" onClick={() => setNavOpen(false)}>知识库</a>
          <a href="/plugins" onClick={() => setNavOpen(false)}>插件</a>
          <a href="/files" onClick={() => setNavOpen(false)}>文件</a>
          <a href="/data-sources" onClick={() => setNavOpen(false)}>数据源</a>
          <a href="/demos" onClick={() => setNavOpen(false)}>业务示例</a>
        </nav>
        <div className="sidebar-spacer" />
        <div className="workspace-chip"><span className="status-dot" /> 默认工作区</div>
        <a className="sidebar-user" href="/settings/profile">管理员 · 设置</a>
      </aside>
      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-header-left"><button className="mobile-nav-button" type="button" aria-label="打开导航" onClick={() => setNavOpen(true)}>☰</button><div><span className="chat-title">新对话</span><span className="chat-context"> · 默认工作区</span></div></div>
          {lastRunId ? <a className="details-button" href={`/runs/${lastRunId}`}>执行详情</a> : <button className="details-button" type="button">执行详情</button>}
        </header>
        <section className="message-column">
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
                {message.role === "assistant" ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown> : <p>{message.content}</p>}
              </article>
            ))
          )}
          {activities.length ? <div className="execution-timeline" aria-live="polite"><span className="rail-kicker">执行进度</span>{activities.slice(-6).map((activity, index) => <span key={`${activity}-${index}`}>{activity}</span>)}</div> : null}
          {error ? <p className="form-error inline-error" role="alert">{error}</p> : null}
        </section>
        <form className="composer-wrap" onSubmit={submit}>
          <div className="context-chips">
            <button type="button" onClick={() => fileInputRef.current?.click()}>＋ 添加文件</button>
            <input ref={fileInputRef} type="file" multiple hidden onChange={chooseFiles} />
            <label className="plugin-select">选择知识库<select aria-label="选择知识库" value={selectedKnowledgeBaseId} onChange={(event) => setSelectedKnowledgeBaseId(event.target.value)}><option value="">不使用知识库</option>{knowledgeBases.filter((base) => base.status === "active").map((base) => <option value={base.id} key={base.id}>{base.name}</option>)}</select></label>
            <label className="plugin-select">连接数据源<select aria-label="选择数据源" value={selectedDataSourceId} onChange={(event) => setSelectedDataSourceId(event.target.value)}><option value="">不使用数据源</option>{dataSources.filter((source) => source.status === "ready").map((source) => <option value={source.id} key={source.id}>{source.name}</option>)}</select></label>
            <label className="plugin-select">使用插件<select aria-label="选择插件" value={selectedPluginId} onChange={(event) => setSelectedPluginId(event.target.value)}><option value="">不使用插件</option>{plugins.filter((plugin) => plugin.published_version_id).map((plugin) => <option value={plugin.published_version_id ?? ""} key={plugin.id}>{plugin.name}</option>)}</select></label>
            {selectedFiles.map((file) => <button className="context-chip" type="button" key={file.id} onClick={() => setSelectedFiles((current) => current.filter((item) => item.id !== file.id))}>{file.name} ×</button>)}
          </div>
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
