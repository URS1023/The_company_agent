import Link from "next/link";

const capabilities = [
  { label: "招投标材料", text: "根据招标要求、企业资料和模板生成可追溯的投标文件。" },
  { label: "经营分析", text: "连接财务数据和补充表格，生成分析、图表和汇报文件。" },
  { label: "企业知识", text: "在对话中选择知识库，回答内容保留来源和页码。" }
];

export default function HomePage() {
  return (
    <main className="landing-shell">
      <div className="landing-mark" aria-hidden="true">CA</div>
      <p className="eyebrow">THE COMPANY AGENT · LOCAL WORKSPACE</p>
      <h1>把一项工作，变成一条可复用的路径。</h1>
      <p className="landing-copy">
        在同一个 Chat 里组合知识、文件、数据和企业程序；每次执行都留下来源、步骤和成果。
      </p>
      <div className="landing-actions">
        <Link className="primary-button" href="/chat">进入工作台</Link>
        <Link className="secondary-button" href="/login">管理员登录</Link>
      </div>
      <section className="capability-grid" aria-label="工作台能力">
        {capabilities.map((item) => (
          <article className="capability-card" key={item.label}>
            <span className="capability-label">{item.label}</span>
            <p>{item.text}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
