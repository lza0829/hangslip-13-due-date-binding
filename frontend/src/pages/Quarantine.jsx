import { useEffect, useState } from "react";
import { api } from "../api";

export default function Quarantine() {
  const [ready, setReady] = useState([]);
  const [overdue, setOverdue] = useState([]);
  const [logs, setLogs] = useState([]);
  const [versions, setVersions] = useState([]);
  const [msg, setMsg] = useState("");

  async function load() {
    const [a, scan, b, v] = await Promise.all([
      api.挂牌列表("?status=" + encodeURIComponent("待取")),
      api.超期扫描(),
      api.隔离列表(),
      api.改日流水().catch(() => []),
    ]);
    setReady(a);
    setOverdue(scan);
    setLogs(b);
    setVersions(v);
  }

  useEffect(() => {
    load().catch((e) => setMsg(e.message));
  }, []);

  async function iso(ticket_no, kind) {
    setMsg("");
    try {
      await api.隔离(ticket_no, {
        kind,
        reason: kind === "超期隔离" ? "逾承诺日未取" : "店内申报丢失",
        operator: "店长",
      });
      setMsg(`${ticket_no} → ${kind}`);
      await load();
    } catch (e) {
      setMsg(e.message);
    }
  }

  const overdueNos = new Set(overdue.map((r) => r.ticket_no));

  return (
    <>
      <section className="panel">
        <h3>超期扫描清单（只认当前取衣日）</h3>
        <p className="msg">{msg}</p>
        {overdue.length === 0 ? (
          <p className="scan-empty">暂无逾取衣日的待取票。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>票号</th>
                <th>门店</th>
                <th>顾客</th>
                <th>取衣日</th>
              </tr>
            </thead>
            <tbody>
              {overdue.map((r) => (
                <tr key={r.ticket_no} className="overdue">
                  <td>{r.ticket_no}</td>
                  <td>{r.store_code}</td>
                  <td>{r.customer_name}</td>
                  <td>{r.due_date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h3>待取转隔离</h3>
        <table>
          <thead>
            <tr>
              <th>票号</th>
              <th>取衣日</th>
              <th>顾客</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {ready.map((r) => {
              const isOver = overdueNos.has(r.ticket_no);
              return (
                <tr key={r.ticket_no} className={isOver ? "overdue" : ""}>
                  <td>{r.ticket_no}</td>
                  <td>{r.due_date}</td>
                  <td>{r.customer_name}</td>
                  <td>
                    <div className="row">
                      <button
                        type="button"
                        disabled={!isOver}
                        title={isOver ? "" : "未逾取衣日，不可超期隔离"}
                        onClick={() => iso(r.ticket_no, "超期隔离")}
                      >
                        超期隔离
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => iso(r.ticket_no, "丢失隔离")}
                      >
                        丢失隔离
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h3>改日流水</h3>
        {versions.length === 0 ? (
          <p className="scan-empty">暂无改约记录。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>票号</th>
                <th>原取衣日</th>
                <th>新取衣日</th>
                <th>原因</th>
                <th>操作人</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((r) => (
                <tr key={r.id}>
                  <td>{r.ticket_no}</td>
                  <td>{r.old_due_date}</td>
                  <td>{r.new_due_date}</td>
                  <td>{r.reason}</td>
                  <td>{r.operator}</td>
                  <td>{r.changed_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h3>隔离流水</h3>
        <table>
          <thead>
            <tr>
              <th>票号</th>
              <th>种类</th>
              <th>原因</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((r) => (
              <tr key={r.id}>
                <td>{r.ticket_no}</td>
                <td>
                  <span className={`badge ${r.kind}`}>{r.kind}</span>
                </td>
                <td>{r.reason}</td>
                <td>{r.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
