import { useState, useEffect, useMemo } from "react";
import liff from "@line/liff";
import { initializeApp } from "firebase/app";
import { getDatabase, ref, onValue, push, remove } from "firebase/database";
import { PlusCircle, BarChart2, Home, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

// ============================================================
const LIFF_ID = "2009693259-XqmMfnwl";
const FIREBASE_CONFIG = {
  databaseURL: "https://expense-tracker-8ffb2-default-rtdb.asia-southeast1.firebasedatabase.app",
};
// ============================================================

const firebaseApp = initializeApp(FIREBASE_CONFIG);
const database = getDatabase(firebaseApp);

const CATEGORIES = {
  income: [
    { id: "salary", label: "เงินเดือน", emoji: "💼" },
    { id: "dividend", label: "เงินปันผล/หุ้น", emoji: "📈" },
    { id: "extra", label: "รายได้พิเศษ", emoji: "⭐" },
    { id: "other_in", label: "อื่นๆ", emoji: "💰" },
  ],
  expense: [
    { id: "food", label: "อาหาร", emoji: "🍱" },
    { id: "medicine", label: "ยาและสุขภาพ", emoji: "💊" },
    { id: "invest", label: "ลงทุน", emoji: "📊" },
    { id: "travel", label: "เดินทาง", emoji: "🚗" },
    { id: "utility", label: "ค่าสาธารณูปโภค", emoji: "💡" },
    { id: "shopping", label: "ช้อปปิ้ง", emoji: "🛍️" },
    { id: "other_ex", label: "อื่นๆ", emoji: "📌" },
  ],
};

const ALL_CATS = [...CATEGORIES.income, ...CATEGORIES.expense];
const getCat = (id) => ALL_CATS.find((c) => c.id === id) || { label: id, emoji: "•" };
const COLORS = ["#6366f1","#f59e0b","#10b981","#f43f5e","#3b82f6","#8b5cf6","#ec4899","#14b8a6","#f97316"];
const MONTHS_TH = ["ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.","ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."];
const fmt = (n) => Number(n).toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Date().toISOString().split("T")[0];

export default function App() {
  const [liffReady, setLiffReady] = useState(false);
  const [user, setUser] = useState(null);
  const [userId, setUserId] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [view, setView] = useState("home");
  const [form, setForm] = useState({ type: "expense", amount: "", category: "food", note: "", date: today() });
  const [month, setMonth] = useState(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() }; });

  // Init LIFF
  useEffect(() => {
    liff.init({ liffId: LIFF_ID })
      .then(async () => {
        if (liff.isLoggedIn()) {
          const profile = await liff.getProfile();
          setUser(profile);
          setUserId(profile.userId);
        } else {
          // ใช้ anonymous user สำหรับทดสอบ
          setUserId("anonymous");
        }
        setLiffReady(true);
      })
      .catch(() => {
        setUserId("anonymous");
        setLiffReady(true);
      });
  }, []);

  // Load จาก Firebase
  useEffect(() => {
    if (!userId) return;
    const txnRef = ref(database, `users/${userId}/transactions`);
    const unsubscribe = onValue(txnRef, (snapshot) => {
      const data = snapshot.val();
      if (data) {
        const list = Object.entries(data).map(([key, val]) => ({ id: key, ...val }));
        list.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
        setTransactions(list);
      } else {
        setTransactions([]);
      }
    });
    return () => unsubscribe();
  }, [userId]);

  const monthTxns = useMemo(() =>
    transactions.filter(t => { const d = new Date(t.date); return d.getFullYear() === month.y && d.getMonth() === month.m; }),
    [transactions, month]
  );

  const totalIncome = monthTxns.filter(t => t.type === "income").reduce((s, t) => s + t.amount, 0);
  const totalExpense = monthTxns.filter(t => t.type === "expense").reduce((s, t) => s + t.amount, 0);
  const balance = transactions.reduce((s, t) => t.type === "income" ? s + t.amount : s - t.amount, 0);

  const last6 = useMemo(() => {
    const arr = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(month.y, month.m - i, 1);
      const y = d.getFullYear(); const m = d.getMonth();
      const txns = transactions.filter(t => { const dd = new Date(t.date); return dd.getFullYear()===y && dd.getMonth()===m; });
      arr.push({ name: MONTHS_TH[m], รายรับ: txns.filter(t=>t.type==="income").reduce((s,t)=>s+t.amount,0), รายจ่าย: txns.filter(t=>t.type==="expense").reduce((s,t)=>s+t.amount,0) });
    }
    return arr;
  }, [transactions, month]);

  const expensePie = useMemo(() => {
    const map = {};
    monthTxns.filter(t=>t.type==="expense").forEach(t => { map[t.category]=(map[t.category]||0)+t.amount; });
    return Object.entries(map).map(([id, v]) => ({ name: getCat(id).label, value: v, emoji: getCat(id).emoji }));
  }, [monthTxns]);

  const addTxn = async () => {
    const amt = parseFloat(form.amount);
    if (!amt || amt <= 0 || !userId) return;
    const txn = { ...form, amount: amt, createdAt: Date.now() };
    await push(ref(database, `users/${userId}/transactions`), txn);
    setForm({ type: "expense", amount: "", category: "food", note: "", date: today() });
    setView("home");
  };

  const delTxn = async (id) => {
    await remove(ref(database, `users/${userId}/transactions/${id}`));
  };

  const changeMonth = (dir) => setMonth(prev => {
    let m = prev.m + dir; let y = prev.y;
    if (m < 0) { m=11; y--; } if (m > 11) { m=0; y++; }
    return { y, m };
  });

  if (!liffReady) return (
    <div style={{ minHeight:"100vh", background:"#0f172a", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", color:"#818cf8", fontFamily:"'Sarabun',sans-serif" }}>
      <div style={{ fontSize:48, marginBottom:16 }}>💰</div>
      <div style={{ fontSize:16 }}>กำลังโหลด...</div>
    </div>
  );

  const card = { background:"rgba(30,27,75,0.8)", border:"1px solid rgba(99,102,241,0.2)", borderRadius:16, padding:16, marginBottom:12 };
  const navBtn = { background:"rgba(99,102,241,0.2)", border:"none", color:"#818cf8", borderRadius:10, width:36, height:36, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" };
  const tabBtn = (active) => ({ flex:1, background: active?"rgba(99,102,241,0.2)":"transparent", border:"none", color: active?"#818cf8":"#475569", borderRadius:12, padding:"8px 0", cursor:"pointer", display:"flex", flexDirection:"column", alignItems:"center", gap:4, fontFamily:"inherit", fontSize:10, fontWeight:600 });
  const labelStyle = { fontSize:12, color:"#818cf8", display:"block", marginBottom:6, fontWeight:600 };
  const inputStyle = { width:"100%", background:"rgba(30,27,75,0.8)", border:"1px solid rgba(99,102,241,0.3)", borderRadius:12, padding:"13px 16px", color:"#f1f5f9", fontSize:18, fontWeight:700, fontFamily:"inherit", outline:"none", boxSizing:"border-box" };

  return (
    <div style={{ minHeight:"100vh", background:"linear-gradient(135deg,#0f172a 0%,#1e1b4b 50%,#0f172a 100%)", fontFamily:"'Sarabun','Noto Sans Thai',sans-serif", color:"#e2e8f0", display:"flex", flexDirection:"column", maxWidth:480, margin:"0 auto" }}>
      <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>

      {/* Header */}
      <div style={{ padding:"24px 20px 0", background:"linear-gradient(180deg,rgba(99,102,241,0.12) 0%,transparent 100%)" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:20 }}>
          <div>
            <div style={{ fontSize:11, color:"#818cf8", letterSpacing:2, textTransform:"uppercase", fontWeight:600 }}>สมุดบัญชีส่วนตัว</div>
            <div style={{ fontSize:22, fontWeight:700, color:"#f1f5f9" }}>{user ? `สวัสดี ${user.displayName.split(" ")[0]} 👋` : "บัญชีรับ-จ่าย 💰"}</div>
          </div>
          {user?.pictureUrl ? <img src={user.pictureUrl} alt="avatar" style={{ width:44, height:44, borderRadius:"50%", border:"2px solid #6366f1" }}/> : <div style={{ width:44, height:44, borderRadius:"50%", background:"linear-gradient(135deg,#6366f1,#8b5cf6)", display:"flex", alignItems:"center", justifyContent:"center", fontSize:22 }}>👩‍⚕️</div>}
        </div>
        <div style={{ background:"linear-gradient(135deg,#6366f1 0%,#4f46e5 50%,#4338ca 100%)", borderRadius:20, padding:"20px 24px", marginBottom:8, boxShadow:"0 8px 32px rgba(99,102,241,0.4)", border:"1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ fontSize:13, color:"rgba(255,255,255,0.75)", marginBottom:4 }}>ยอดคงเหลือรวม</div>
          <div style={{ fontSize:34, fontWeight:700, color:"#fff", letterSpacing:-1 }}>฿{fmt(balance)}</div>
          <div style={{ display:"flex", gap:12, marginTop:16 }}>
            <div style={{ flex:1, background:"rgba(255,255,255,0.12)", borderRadius:12, padding:"10px 14px" }}>
              <div style={{ fontSize:11, color:"rgba(255,255,255,0.65)", marginBottom:2 }}>↑ รายรับเดือนนี้</div>
              <div style={{ fontWeight:700, color:"#6ee7b7", fontSize:15 }}>฿{fmt(totalIncome)}</div>
            </div>
            <div style={{ flex:1, background:"rgba(255,255,255,0.12)", borderRadius:12, padding:"10px 14px" }}>
              <div style={{ fontSize:11, color:"rgba(255,255,255,0.65)", marginBottom:2 }}>↓ รายจ่ายเดือนนี้</div>
              <div style={{ fontWeight:700, color:"#fda4af", fontSize:15 }}>฿{fmt(totalExpense)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex:1, overflowY:"auto", padding:"0 20px 100px" }}>

        {/* HOME */}
        {view === "home" && (
          <>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", margin:"20px 0 12px" }}>
              <button onClick={() => changeMonth(-1)} style={navBtn}><ChevronLeft size={18}/></button>
              <div style={{ fontWeight:700, fontSize:16, color:"#c7d2fe" }}>{MONTHS_TH[month.m]} {month.y+543}</div>
              <button onClick={() => changeMonth(1)} style={navBtn}><ChevronRight size={18}/></button>
            </div>
            {monthTxns.length === 0
              ? <div style={{ textAlign:"center", color:"#475569", marginTop:40 }}><div style={{ fontSize:48 }}>📋</div><div style={{ fontSize:14, marginTop:8 }}>ยังไม่มีรายการในเดือนนี้</div><div style={{ fontSize:12, color:"#334155", marginTop:4 }}>ส่งสลิปใน LINE หรือกด + เพื่อเพิ่ม</div></div>
              : <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                  {monthTxns.map(t => {
                    const cat = getCat(t.category);
                    const isIn = t.type === "income";
                    const d = new Date(t.date);
                    return (
                      <div key={t.id} style={{ background:"rgba(30,27,75,0.8)", border:"1px solid rgba(99,102,241,0.15)", borderRadius:14, padding:"12px 16px", display:"flex", alignItems:"center", gap:12 }}>
                        <div style={{ width:42, height:42, borderRadius:12, flexShrink:0, background: isIn?"rgba(16,185,129,0.15)":"rgba(244,63,94,0.15)", border:`1px solid ${isIn?"rgba(16,185,129,0.3)":"rgba(244,63,94,0.3)"}`, display:"flex", alignItems:"center", justifyContent:"center", fontSize:20 }}>{cat.emoji}</div>
                        <div style={{ flex:1, minWidth:0 }}>
                          <div style={{ fontWeight:600, fontSize:14, color:"#e2e8f0", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{cat.label}{t.note ? ` · ${t.note}` : ""}{t.source === "slip" ? " 📄" : ""}</div>
                          <div style={{ fontSize:11, color:"#64748b", marginTop:2 }}>{d.getDate()} {MONTHS_TH[d.getMonth()]} {d.getFullYear()+543}</div>
                        </div>
                        <div style={{ textAlign:"right", flexShrink:0 }}>
                          <div style={{ fontWeight:700, fontSize:15, color: isIn?"#6ee7b7":"#fda4af" }}>{isIn?"+":"-"}฿{fmt(t.amount)}</div>
                          <button onClick={() => delTxn(t.id)} style={{ background:"none", border:"none", color:"#475569", cursor:"pointer", padding:"2px 0 0", display:"flex", alignItems:"center", justifyContent:"flex-end" }}><Trash2 size={13}/></button>
                        </div>
                      </div>
                    );
                  })}
                </div>
            }
          </>
        )}

        {/* ADD */}
        {view === "add" && (
          <div style={{ paddingTop:20 }}>
            <div style={{ fontWeight:700, fontSize:18, marginBottom:20, color:"#c7d2fe" }}>เพิ่มรายการใหม่</div>
            <div style={{ display:"flex", background:"rgba(30,27,75,0.8)", borderRadius:14, padding:4, marginBottom:20, border:"1px solid rgba(99,102,241,0.2)" }}>
              {[["expense","รายจ่าย","#f43f5e"],["income","รายรับ","#10b981"]].map(([v,l,c]) => (
                <button key={v} onClick={() => setForm(f=>({...f,type:v,category:v==="income"?"salary":"food"}))} style={{ flex:1, padding:"10px 0", borderRadius:10, border:"none", fontFamily:"inherit", fontWeight:700, fontSize:15, cursor:"pointer", background: form.type===v?`linear-gradient(135deg,${c}dd,${c}99)`:"transparent", color: form.type===v?"#fff":"#64748b" }}>{l}</button>
              ))}
            </div>
            <div style={{ marginBottom:16 }}><label style={labelStyle}>จำนวนเงิน (บาท)</label><input type="number" inputMode="decimal" placeholder="0.00" value={form.amount} onChange={e=>setForm(f=>({...f,amount:e.target.value}))} style={inputStyle}/></div>
            <div style={{ marginBottom:16 }}>
              <label style={labelStyle}>หมวดหมู่</label>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8 }}>
                {CATEGORIES[form.type].map(cat => (
                  <button key={cat.id} onClick={() => setForm(f=>({...f,category:cat.id}))} style={{ background: form.category===cat.id?"rgba(99,102,241,0.4)":"rgba(30,27,75,0.6)", border:`1px solid ${form.category===cat.id?"rgba(99,102,241,0.8)":"rgba(99,102,241,0.15)"}`, borderRadius:12, padding:"10px 6px", cursor:"pointer", fontFamily:"inherit", color: form.category===cat.id?"#c7d2fe":"#64748b", fontSize:12, fontWeight:600, display:"flex", flexDirection:"column", alignItems:"center", gap:4 }}>
                    <span style={{ fontSize:22 }}>{cat.emoji}</span><span>{cat.label}</span>
                  </button>
                ))}
              </div>
            </div>
            <div style={{ marginBottom:16 }}><label style={labelStyle}>หมายเหตุ</label><input type="text" placeholder="เช่น ข้าวเที่ยง..." value={form.note} onChange={e=>setForm(f=>({...f,note:e.target.value}))} style={{...inputStyle,fontSize:14,fontWeight:400}}/></div>
            <div style={{ marginBottom:24 }}><label style={labelStyle}>วันที่</label><input type="date" value={form.date} onChange={e=>setForm(f=>({...f,date:e.target.value}))} style={{...inputStyle,fontSize:14,fontWeight:400,colorScheme:"dark"}}/></div>
            <button onClick={addTxn} style={{ width:"100%", padding:16, borderRadius:14, border:"none", background:"linear-gradient(135deg,#6366f1,#4f46e5)", color:"#fff", fontWeight:700, fontSize:16, cursor:"pointer", fontFamily:"inherit", boxShadow:"0 4px 20px rgba(99,102,241,0.5)" }}>บันทึกรายการ ✓</button>
          </div>
        )}

        {/* REPORT */}
        {view === "report" && (
          <div style={{ paddingTop:20 }}>
            <div style={{ fontWeight:700, fontSize:18, marginBottom:4, color:"#c7d2fe" }}>สรุปรายงาน</div>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", margin:"12px 0 20px" }}>
              <button onClick={() => changeMonth(-1)} style={navBtn}><ChevronLeft size={18}/></button>
              <div style={{ fontWeight:700, fontSize:16, color:"#c7d2fe" }}>{MONTHS_TH[month.m]} {month.y+543}</div>
              <button onClick={() => changeMonth(1)} style={navBtn}><ChevronRight size={18}/></button>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:16 }}>
              {[{label:"รายรับ",val:totalIncome,color:"#10b981",bg:"rgba(16,185,129,0.1)",border:"rgba(16,185,129,0.3)",e:"↑"},{label:"รายจ่าย",val:totalExpense,color:"#f43f5e",bg:"rgba(244,63,94,0.1)",border:"rgba(244,63,94,0.3)",e:"↓"},{label:"ออมได้",val:totalIncome-totalExpense,color:"#6366f1",bg:"rgba(99,102,241,0.1)",border:"rgba(99,102,241,0.3)",e:"🎯"},{label:"รายการ",val:monthTxns.length,color:"#f59e0b",bg:"rgba(245,158,11,0.1)",border:"rgba(245,158,11,0.3)",e:"📋",noFmt:true}].map(({label,val,color,bg,border,e,noFmt})=>(
                <div key={label} style={{ background:bg, border:`1px solid ${border}`, borderRadius:14, padding:14 }}>
                  <div style={{ fontSize:11, color:"#94a3b8", marginBottom:4 }}>{e} {label}</div>
                  <div style={{ fontWeight:700, color, fontSize:noFmt?22:15 }}>{noFmt?val:`฿${fmt(val)}`}</div>
                </div>
              ))}
            </div>
            <div style={{ ...card }}>
              <div style={{ fontSize:13, fontWeight:600, color:"#818cf8", marginBottom:12 }}>รายรับ-จ่าย 6 เดือน</div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={last6} barSize={14}>
                  <XAxis dataKey="name" tick={{fill:"#64748b",fontSize:11}} axisLine={false} tickLine={false}/>
                  <YAxis hide/>
                  <Tooltip contentStyle={{background:"#1e1b4b",border:"1px solid #6366f1",borderRadius:10,fontSize:12,color:"#e2e8f0"}} formatter={v=>`฿${fmt(v)}`}/>
                  <Bar dataKey="รายรับ" fill="#10b981" radius={[4,4,0,0]}/>
                  <Bar dataKey="รายจ่าย" fill="#f43f5e" radius={[4,4,0,0]}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {expensePie.length > 0 && (
              <div style={{ ...card }}>
                <div style={{ fontSize:13, fontWeight:600, color:"#818cf8", marginBottom:12 }}>แยกตามหมวดหมู่</div>
                {[...expensePie].sort((a,b)=>b.value-a.value).map((item,i)=>{
                  const pct = totalExpense>0?item.value/totalExpense*100:0;
                  return (
                    <div key={item.name} style={{ marginBottom:10 }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                        <span style={{ fontSize:13, color:"#cbd5e1" }}>{item.emoji} {item.name}</span>
                        <span style={{ fontSize:13, fontWeight:600, color:COLORS[i%COLORS.length] }}>฿{fmt(item.value)}</span>
                      </div>
                      <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:99, height:6, overflow:"hidden" }}>
                        <div style={{ width:`${pct}%`, height:"100%", background:COLORS[i%COLORS.length], borderRadius:99 }}/>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Nav */}
      <div style={{ position:"fixed", bottom:0, left:"50%", transform:"translateX(-50%)", width:"100%", maxWidth:480, background:"rgba(15,23,42,0.95)", backdropFilter:"blur(20px)", borderTop:"1px solid rgba(99,102,241,0.2)", display:"flex", alignItems:"center", padding:"10px 16px 20px", gap:8, zIndex:100 }}>
        <button onClick={()=>setView("home")} style={tabBtn(view==="home")}><Home size={20}/><span>รายการ</span></button>
        <button onClick={()=>setView("add")} style={{ width:60, height:60, borderRadius:"50%", border:"3px solid rgba(99,102,241,0.5)", background:"linear-gradient(135deg,#6366f1,#4f46e5)", color:"#fff", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", boxShadow:"0 4px 24px rgba(99,102,241,0.6)", flexShrink:0 }}><PlusCircle size={28}/></button>
        <button onClick={()=>setView("report")} style={tabBtn(view==="report")}><BarChart2 size={20}/><span>รายงาน</span></button>
      </div>

      <style>{`input[type=number]::-webkit-inner-spin-button{-webkit-appearance:none} *{-webkit-tap-highlight-color:transparent} ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:rgba(99,102,241,0.3);border-radius:2px}`}</style>
    </div>
  );
}
