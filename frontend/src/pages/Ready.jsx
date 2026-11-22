import { useEffect, useState } from "react";
import { api } from "../api";

export default function Ready() {
  const [rows, setRows] = useState([]);
  const [codes, setCodes] = useState({});
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");

  async function load() {
    // 后端已按取衣日（唯一权威日）升序返回，前端不再自行排序。
    setRows(await api.挂牌列表("?status=" + encodeURIComponent("待取")));
  }

  useEffect(() => {
    load().catch((e) => setMsg(e.message));
  }, []);

  async function pick(ticket_no) {
    setMsg("");
    try {
      await api.取衣(ticket_no, {
        pickup_code: codes[ticket_no] || "",
        operator: "柜员",
      });
      setMsg(`${ticket_no} 已取衣核销`);
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
        operator: "柜员",
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
      <h3>待取核销（按取衣日排序）</h3>
      <p className={`msg ${msg.includes("成功") || msg.includes("已取") ? "ok" : ""}`}>
        {msg}
      </p>
      <table>
        <thead>
          <tr>
            <th>票号</th>
            <th>顾客</th>
            <th>取衣日</th>
            <th>超期</th>
            <th>暗码核销</th>
            <th>改约取衣日</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticket_no} className={r.超期 ? "overdue" : ""}>
              <td>{r.ticket_no}</td>
              <td>{r.customer_name}</td>
              <td>{r.due_date}</td>
              <td>
                {r.超期 ? <span className="badge 超期">超期</span> : "—"}
              </td>
              <td>
                <div className="reschedule">
                  <input
                    placeholder="输入暗码"
                    value={codes[r.ticket_no] || ""}
                    onChange={(e) =>
                      setCodes({ ...codes, [r.ticket_no]: e.target.value })
                    }
                  />
                  <button type="button" onClick={() => pick(r.ticket_no)}>
                    核销取衣
                  </button>
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
