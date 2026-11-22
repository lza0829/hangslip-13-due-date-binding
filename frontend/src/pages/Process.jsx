import { useEffect, useState } from "react";
import { api } from "../api";

const NEXT = {
  已收: ["水洗", "烘干", "熨烫", "待取"],
  水洗: ["烘干", "熨烫", "待取"],
  烘干: ["熨烫", "待取"],
  熨烫: ["待取"],
};

export default function Process() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");

  async function load() {
    const all = await api.挂牌列表();
    setRows(all.filter((r) => !["已取", "超期隔离", "丢失隔离"].includes(r.status)));
  }

  useEffect(() => {
    load().catch((e) => setMsg(e.message));
  }, []);

  async function go(ticket_no, to_status) {
    setMsg("");
    try {
      await api.推进(ticket_no, { to_status, operator: "工序员" });
      setMsg(`${ticket_no} → ${to_status}`);
      await load();
    } catch (e) {
      setMsg(e.message);
    }
  }

  async function reschedule(ticket_no) {
    setMsg("");
    const f = form[ticket_no] || {};
    try {
      await api.改约(ticket_no, {
        new_due_date: f.new_due_date || "",
        reason: f.reason || "",
        operator: "工序员",
      });
      setMsg(`${ticket_no} 改约成功，取衣日已更新`);
      setForm((prev) => {
        const next = { ...prev };
        delete next[ticket_no];
        return next;
      });
      await load();
    } catch (e) {
      setMsg(e.message);
    }
  }

  return (
    <section className="panel">
      <h3>工序轨</h3>
      <p className={`msg ${msg.includes("→") || msg.includes("成功") ? "ok" : ""}`}>
        {msg}
      </p>
      <table>
        <thead>
          <tr>
            <th>票号</th>
            <th>门店</th>
            <th>顾客</th>
            <th>现行</th>
            <th>取衣日</th>
            <th>推进</th>
            <th>改约取衣日</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticket_no}>
              <td>{r.ticket_no}</td>
              <td>{r.store_code}</td>
              <td>{r.customer_name}</td>
              <td>
                <span className={`badge ${r.status}`}>{r.status}</span>
              </td>
              <td>{r.due_date}</td>
              <td>
                <div className="row">
                  {(NEXT[r.status] || []).map((s) => (
                    <button key={s} type="button" className="ghost" onClick={() => go(r.ticket_no, s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </td>
              <td>
                <div className="reschedule">
                  <input
                    type="date"
                    aria-label="新取衣日"
                    value={form[r.ticket_no]?.new_due_date || ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        [r.ticket_no]: {
                          ...(form[r.ticket_no] || {}),
                          new_due_date: e.target.value,
                        },
                      })
                    }
                  />
                  <input
                    className="reason"
                    placeholder="改约原因（必填）"
                    value={form[r.ticket_no]?.reason || ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        [r.ticket_no]: {
                          ...(form[r.ticket_no] || {}),
                          reason: e.target.value,
                        },
                      })
                    }
                  />
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => reschedule(r.ticket_no)}
                  >
                    改约
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
