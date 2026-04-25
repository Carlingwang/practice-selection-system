import os
import json
import io
import random
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook, load_workbook
from models import (
    init_db, get_db, check_admin, get_setting, set_setting, DB_PATH
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

init_db()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def get_system_mode():
    """获取系统模式: close / preview / open"""
    return get_setting("system_mode") or "close"

def check_time_based_open():
    """定时开放：仅在timer_enabled=1时自动切换，不影响手动操作"""
    if get_setting("timer_enabled") != "1":
        return
    open_time = get_setting("open_time")
    close_time = get_setting("close_time")
    if not open_time or not close_time:
        return
    try:
        now = datetime.now()
        open_dt = datetime.strptime(open_time, "%Y-%m-%dT%H:%M")
        close_dt = datetime.strptime(close_time, "%Y-%m-%dT%H:%M")
        if open_dt <= now <= close_dt:
            if get_system_mode() in ("close", "preview"):
                set_setting("system_mode", "open")
        elif now > close_dt:
            if get_system_mode() in ("open", "preview"):
                set_setting("system_mode", "close")
    except:
        pass

def is_system_open():
    """系统是否完全开放（可选择）"""
    check_time_based_open()
    return get_system_mode() == "open"

def is_system_preview():
    """系统是否处于预览模式（可浏览不可选）"""
    check_time_based_open()
    return get_system_mode() == "preview"

def can_view_positions():
    """学生是否可以查看岗位列表（预览或开放都可）"""
    check_time_based_open()
    return get_system_mode() in ("preview", "open")

# ========== Admin Auth ==========
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if check_admin(u, p):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("账号或密码错误", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# ========== Admin Dashboard ==========
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    stats = {}
    stats["total_students"] = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    stats["submitted"] = conn.execute("SELECT COUNT(*) FROM students WHERE has_submitted=1").fetchone()[0]
    stats["total_positions"] = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    stats["classes"] = conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0]
    positions = conn.execute("""
        SELECT p.*, 
               GROUP_CONCAT(c.name) as class_names,
               GROUP_CONCAT(pc.class_id) as visible_class_ids
        FROM positions p
        LEFT JOIN position_classes pc ON p.id = pc.position_id
        LEFT JOIN classes c ON pc.class_id = c.id
        GROUP BY p.id ORDER BY p.id
    """).fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, positions=positions,
                           system_mode=get_system_mode(),
                           open_time=get_setting("open_time"),
                           close_time=get_setting("close_time"), random_order=get_setting("random_order", "1"))

# ========== System Control ==========
@app.route("/admin/system", methods=["POST"])
@admin_required
def admin_system():
    action = request.form.get("action")
    if action == "open":
        set_setting("system_mode", "open")
        set_setting("timer_enabled", "0")
        flash("系统已开放（学生可选择岗位）", "success")
    elif action == "preview":
        set_setting("system_mode", "preview")
        set_setting("timer_enabled", "0")
        flash("系统已进入预览模式（学生可浏览岗位但不能选择）", "info")
    elif action == "close":
        set_setting("system_mode", "close")
        flash("系统已关闭", "warning")
    elif action == "reset":
        conn = get_db()
        conn.execute("DELETE FROM submissions")
        conn.execute("UPDATE students SET has_submitted=0, submitted_at=NULL, assigned_position_id=NULL")
        conn.execute("UPDATE positions SET current_count=0")
        conn.commit()
        conn.close()
        flash("已重置所有选择数据", "warning")
    elif action == "set_random":
        random_order = request.form.get("random_order", "0")
        set_setting("random_order", random_order)
        flash(f"岗位排序已设置为：{'随机展示' if random_order == '1' else '顺序展示'}", "success")
    return redirect(url_for("admin_dashboard"))

# 设置定时时间（AJAX接口）
@app.route("/admin/set_schedule", methods=["POST"])
@admin_required
def admin_set_schedule():
    """确认设定定时开放/关闭时间，保存后由 check_time_based_open 自动切换"""
    data = request.get_json()
    open_time = data.get("open_time", "")
    close_time = data.get("close_time", "")
    if not open_time or not close_time:
        return jsonify(success=False, message="时间不能为空")
    try:
        open_dt = datetime.strptime(open_time, "%Y-%m-%dT%H:%M")
        close_dt = datetime.strptime(close_time, "%Y-%m-%dT%H:%M")
    except ValueError:
        return jsonify(success=False, message="时间格式错误")
    if close_dt <= open_dt:
        return jsonify(success=False, message="结束时间必须晚于开始时间")
    # 保存时间设置
    set_setting("open_time", open_dt.strftime("%Y-%m-%dT%H:%M"))
    set_setting("close_time", close_dt.strftime("%Y-%m-%dT%H:%M"))
    set_setting("timer_enabled", "1")
    return jsonify(success=True)


# ========== Class Management ==========
@app.route("/admin/classes")
@admin_required
def admin_classes():
    conn = get_db()
    classes = conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.class_id=c.id) as student_count
        FROM classes c ORDER BY c.name
    """).fetchall()
    conn.close()
    return render_template("admin_classes.html", classes=classes)

@app.route("/admin/classes/add", methods=["POST"])
@admin_required
def admin_classes_add():
    name = request.form.get("name", "").strip()
    if name:
        conn = get_db()
        try:
            conn.execute("INSERT INTO classes (name) VALUES (?)", (name,))
            conn.commit()
            flash(f"班级「{name}」添加成功", "success")
        except:
            flash("班级已存在", "danger")
        conn.close()
    return redirect(url_for("admin_classes"))

@app.route("/admin/classes/delete/<int:cid>")
@admin_required
def admin_classes_delete(cid):
    conn = get_db()
    conn.execute("UPDATE students SET class_id=NULL WHERE class_id=?", (cid,))
    conn.execute("DELETE FROM position_classes WHERE class_id=?", (cid,))
    conn.execute("DELETE FROM classes WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    flash("班级已删除", "warning")
    return redirect(url_for("admin_classes"))

# ========== Student Management ==========
@app.route("/admin/students")
@admin_required
def admin_students():
    conn = get_db()
    classes = conn.execute("SELECT * FROM classes ORDER BY name").fetchall()
    selected_class = request.args.get("class_id", "")
    if selected_class:
        students = conn.execute("""
            SELECT s.*, c.name as class_name FROM students s
            LEFT JOIN classes c ON s.class_id=c.id WHERE s.class_id=?
            ORDER BY c.name, s.student_id
        """, (selected_class,)).fetchall()
    else:
        students = conn.execute("""
            SELECT s.*, c.name as class_name FROM students s
            LEFT JOIN classes c ON s.class_id=c.id ORDER BY c.name, s.student_id
        """).fetchall()
    conn.close()
    return render_template("admin_students.html", students=students, classes=classes, selected_class=selected_class)

@app.route("/admin/students/import", methods=["POST"])
@admin_required
def admin_students_import():
    f = request.files.get("file")
    class_id = request.form.get("class_id")
    if not f or not class_id:
        flash("请选择文件和班级", "danger")
        return redirect(url_for("admin_students"))
    try:
        wb = load_workbook(f)
        ws = wb.active
        conn = get_db()
        count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] and row[1]:
                try:
                    conn.execute("INSERT OR IGNORE INTO students (name, student_id, class_id) VALUES (?, ?, ?)",
                                (str(row[0]).strip(), str(row[1]).strip(), int(class_id)))
                    count += 1
                except:
                    pass
        conn.commit()
        conn.close()
        flash(f"成功导入 {count} 名学生", "success")
    except Exception as e:
        flash(f"导入失败: {e}", "danger")
    return redirect(url_for("admin_students"))

@app.route("/admin/students/template")
def student_template():
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "学号"])
    ws.append(["张三", "2021001"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="student_template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/admin/students/delete/<int:sid>")
@admin_required
def admin_students_delete(sid):
    conn = get_db()
    s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if s and s["has_submitted"]:
        conn.execute("UPDATE positions SET current_count=MAX(0,current_count-1) WHERE id IN (SELECT position_id FROM submissions WHERE student_id=?)", (sid,))
    conn.execute("DELETE FROM submissions WHERE student_id=?", (sid,))
    conn.execute("DELETE FROM student_position_assign WHERE student_id=?", (sid,))
    conn.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    flash("学生已删除", "warning")
    return redirect(url_for("admin_students"))

@app.route("/admin/students/batch_delete", methods=["POST"])
@admin_required
def admin_students_batch_delete():
    ids = request.form.get("ids", "")
    if not ids:
        flash("未选择学生", "warning")
        return redirect(url_for("admin_students"))
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        flash("无效的学生ID", "warning")
        return redirect(url_for("admin_students"))
    conn = get_db()
    for sid in id_list:
        s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if s and s["has_submitted"]:
            conn.execute("UPDATE positions SET current_count=MAX(0,current_count-1) WHERE id IN (SELECT position_id FROM submissions WHERE student_id=?)", (sid,))
        conn.execute("DELETE FROM submissions WHERE student_id=?", (sid,))
        conn.execute("DELETE FROM student_position_assign WHERE student_id=?", (sid,))
        conn.execute("DELETE FROM students WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    flash(f"已删除 {len(id_list)} 名学生", "success")
    return redirect(url_for("admin_students"))

# ========== Position Management ==========
@app.route("/admin/positions")
@admin_required
def admin_positions():
    conn = get_db()
    positions = conn.execute("""
        SELECT p.*, 
               GROUP_CONCAT(c.name) as class_names,
               GROUP_CONCAT(pc.class_id) as visible_class_ids
        FROM positions p
        LEFT JOIN position_classes pc ON p.id = pc.position_id
        LEFT JOIN classes c ON pc.class_id = c.id
        GROUP BY p.id ORDER BY p.id
    """).fetchall()
    classes = conn.execute("SELECT * FROM classes ORDER BY name").fetchall()
    conn.close()
    return render_template("admin_positions.html", positions=positions, classes=classes)

@app.route("/admin/positions/add", methods=["POST"])
@admin_required
def admin_positions_add():
    base = request.form.get("base_name", "").strip()
    quota = int(request.form.get("quota", 1))
    instructor = request.form.get("instructor", "").strip()
    requirements = request.form.get("requirements", "").strip()
    class_ids = request.form.getlist("class_ids")
    if not base:
        flash("请填写实习基地名称", "danger")
        return redirect(url_for("admin_positions"))
    conn = get_db()
    cur = conn.execute("INSERT INTO positions (base_name, quota, instructor, requirements) VALUES (?, ?, ?, ?)",
                       (base, quota, instructor, requirements))
    pid = cur.lastrowid
    for cid in class_ids:
        conn.execute("INSERT OR IGNORE INTO position_classes (position_id, class_id) VALUES (?, ?)", (pid, int(cid)))
    conn.commit()
    conn.close()
    flash(f"岗位「{base}」添加成功", "success")
    return redirect(url_for("admin_positions"))

@app.route("/admin/positions/edit/<int:pid>", methods=["POST"])
@admin_required
def admin_positions_edit(pid):
    base = request.form.get("base_name", "").strip()
    quota = int(request.form.get("quota", 1))
    instructor = request.form.get("instructor", "").strip()
    requirements = request.form.get("requirements", "").strip()
    class_ids = request.form.getlist("class_ids")
    conn = get_db()
    conn.execute("UPDATE positions SET base_name=?, quota=?, instructor=?, requirements=? WHERE id=?",
                 (base, quota, instructor, requirements, pid))
    conn.execute("DELETE FROM position_classes WHERE position_id=?", (pid,))
    for cid in class_ids:
        conn.execute("INSERT OR IGNORE INTO position_classes (position_id, class_id) VALUES (?, ?)", (pid, int(cid)))
    conn.commit()
    conn.close()
    flash("岗位已更新", "success")
    return redirect(url_for("admin_positions"))

@app.route("/admin/positions/delete/<int:pid>")
@admin_required
def admin_positions_delete(pid):
    conn = get_db()
    conn.execute("UPDATE students SET has_submitted=0, submitted_at=NULL, assigned_position_id=NULL WHERE id IN (SELECT student_id FROM submissions WHERE position_id=?)", (pid,))
    conn.execute("DELETE FROM submissions WHERE position_id=?", (pid,))
    conn.execute("DELETE FROM student_position_assign WHERE position_id=?", (pid,))
    conn.execute("DELETE FROM position_classes WHERE position_id=?", (pid,))
    conn.execute("DELETE FROM positions WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    flash("岗位已删除", "warning")
    return redirect(url_for("admin_positions"))

@app.route("/admin/positions/batch_delete", methods=["POST"])
@admin_required
def admin_positions_batch_delete():
    ids = request.form.get("ids", "")
    if not ids:
        flash("未选择岗位", "warning")
        return redirect(url_for("admin_positions"))
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        flash("无效的岗位ID", "warning")
        return redirect(url_for("admin_positions"))
    conn = get_db()
    for pid in id_list:
        conn.execute("UPDATE students SET has_submitted=0, submitted_at=NULL, assigned_position_id=NULL WHERE id IN (SELECT student_id FROM submissions WHERE position_id=?)", (pid,))
        conn.execute("DELETE FROM submissions WHERE position_id=?", (pid,))
        conn.execute("DELETE FROM student_position_assign WHERE position_id=?", (pid,))
        conn.execute("DELETE FROM position_classes WHERE position_id=?", (pid,))
        conn.execute("DELETE FROM positions WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    flash(f"已删除 {len(id_list)} 个岗位", "success")
    return redirect(url_for("admin_positions"))

@app.route("/admin/positions/import", methods=["POST"])
@admin_required
def admin_positions_import():
    f = request.files.get("file")
    if not f:
        flash("请选择文件", "danger")
        return redirect(url_for("admin_positions"))
    try:
        wb = load_workbook(f)
        ws = wb.active
        conn = get_db()
        count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            base = str(row[0]).strip() if row[0] else ""
            quota = int(row[1]) if row[1] else 1
            instructor = str(row[2]).strip() if row[2] else ""
            req = str(row[3]).strip() if row[3] else ""
            class_names = str(row[4]).strip() if row[4] else ""
            if base:
                cur = conn.execute("INSERT INTO positions (base_name, quota, instructor, requirements) VALUES (?,?,?,?)",
                                   (base, quota, instructor, req))
                pid = cur.lastrowid
                if class_names:
                    for cn in class_names.split(","):
                        cn = cn.strip()
                        cr = conn.execute("SELECT id FROM classes WHERE name=?", (cn,)).fetchone()
                        if cr:
                            conn.execute("INSERT OR IGNORE INTO position_classes (position_id, class_id) VALUES (?,?)", (pid, cr["id"]))
                count += 1
        conn.commit()
        conn.close()
        flash(f"成功导入 {count} 个岗位", "success")
    except Exception as e:
        flash(f"导入失败: {e}", "danger")
    return redirect(url_for("admin_positions"))

@app.route("/admin/positions/template")
def position_template():
    wb = Workbook()
    ws = wb.active
    ws.append(["实习基地", "配额人数", "指导教师", "备注要求", "可见班级(逗号分隔)"])
    ws.append(["XX医院", 5, "张老师", "需持护士证", "护理1班,护理2班"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="position_template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ========== Assign Position to Student ==========
@app.route("/admin/assign")
@admin_required
def admin_assign():
    conn = get_db()
    students = conn.execute("""
        SELECT s.*, c.name as class_name FROM students s
        LEFT JOIN classes c ON s.class_id=c.id ORDER BY c.name, s.student_id
    """).fetchall()
    positions = conn.execute("SELECT * FROM positions ORDER BY base_name").fetchall()
    assigns = conn.execute("""
        SELECT spa.student_id, spa.position_id, s.name as sname, s.student_id as sid, p.base_name
        FROM student_position_assign spa
        JOIN students s ON spa.student_id=s.id
        JOIN positions p ON spa.position_id=p.id
        ORDER BY s.student_id
    """).fetchall()
    conn.close()
    return render_template("admin_assign.html", students=students, positions=positions, assigns=assigns)

@app.route("/admin/assign/add", methods=["POST"])
@admin_required
def admin_assign_add():
    sid = request.form.get("student_id")
    pid = request.form.get("position_id")
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO student_position_assign (student_id, position_id) VALUES (?, ?)", (int(sid), int(pid)))
    conn.commit()
    conn.close()
    flash("指定成功", "success")
    return redirect(url_for("admin_assign"))

@app.route("/admin/assign/delete/<int:sid>")
@admin_required
def admin_assign_delete(sid):
    conn = get_db()
    conn.execute("DELETE FROM student_position_assign WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()
    flash("已取消指定", "warning")
    return redirect(url_for("admin_assign"))

@app.route("/admin/assign/import", methods=["POST"])
@admin_required
def admin_assign_import():
    f = request.files.get("file")
    if not f:
        flash("请选择文件", "danger")
        return redirect(url_for("admin_assign"))
    try:
        wb = load_workbook(f)
        ws = wb.active
        conn = get_db()
        count = 0
        errors = []
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            sid = str(row[0]).strip() if row[0] else ""
            pname = str(row[1]).strip() if row[1] else ""
            if not sid or not pname:
                continue
            student = conn.execute("SELECT id FROM students WHERE student_id=?", (sid,)).fetchone()
            position = conn.execute("SELECT id FROM positions WHERE base_name=?", (pname,)).fetchone()
            if not student:
                errors.append(f"第{i}行：学号「{sid}」不存在")
                continue
            if not position:
                errors.append(f"第{i}行：岗位「{pname}」不存在")
                continue
            conn.execute("INSERT OR REPLACE INTO student_position_assign (student_id, position_id) VALUES (?, ?)",
                        (student["id"], position["id"]))
            count += 1
        conn.commit()
        conn.close()
        if count:
            flash(f"成功指定 {count} 条记录", "success")
        if errors:
            flash("；".join(errors[:10]), "warning")
    except Exception as e:
        flash(f"导入失败: {e}", "danger")
    return redirect(url_for("admin_assign"))

@app.route("/admin/assign/template")
def assign_template():
    wb = Workbook()
    ws = wb.active
    ws.append(["学号", "岗位名称"])
    ws.append(["2021001", "XX医院"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="assign_template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ========== Export ==========
@app.route("/admin/export")
@admin_required
def admin_export():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.student_id, s.name, c.name as class_name,
               p.base_name, p.instructor, p.requirements, sub.created_at
        FROM submissions sub
        JOIN students s ON sub.student_id=s.id
        LEFT JOIN classes c ON s.class_id=c.id
        JOIN positions p ON sub.position_id=p.id
        ORDER BY c.name, s.student_id
    """).fetchall()
    wb = Workbook()
    ws = wb.active
    ws.title = "选择结果"
    ws.append(["学号", "姓名", "班级", "实习基地", "指导教师", "备注要求", "提交时间"])
    for r in rows:
        ws.append([r["student_id"], r["name"], r["class_name"], r["base_name"], r["instructor"], r["requirements"], r["created_at"]])
    ws2 = wb.create_sheet("岗位统计")
    ws2.append(["实习基地", "配额", "已选", "剩余"])
    stats = conn.execute("SELECT base_name, quota, current_count FROM positions ORDER BY base_name").fetchall()
    for s in stats:
        ws2.append([s["base_name"], s["quota"], s["current_count"], s["quota"] - s["current_count"]])
    conn.close()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"实习选岗结果_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ========== Student API ==========
@app.route("/api/system_status")
def api_system_status():
    mode = get_system_mode()
    return jsonify({
        "mode": mode,
        "open": mode == "open",
        "preview": mode == "preview",
        "can_view": mode in ("preview", "open")
    })

@app.route("/api/positions/<int:class_id>")
@app.route("/api/positions/<int:student_id>")
def api_positions(student_id):
    """获取学生可选的岗位列表"""
    conn = get_db()
    
    # 检查系统状态
    mode = get_setting("system_mode", "close")
    if mode == "close":
        conn.close()
        return jsonify([])
    
    # 获取学生信息
    student = conn.execute("SELECT id, class_id FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        conn.close()
        return jsonify([])
    
    student_db_id = student["id"]
    class_id = student["class_id"]
    random_order = get_setting("random_order", "0") == "1"
    
    # 获取该学生已提交的岗位
    existing = conn.execute("SELECT position_id FROM submissions WHERE student_id=?", (student_db_id,)).fetchone()
    submitted_position_id = existing["position_id"] if existing else None
    
    # 获取该学生班级可见的岗位
    if class_id:
        positions = conn.execute("""
            SELECT p.id, p.base_name, p.quota, p.current_count, p.instructor, p.requirements
            FROM positions p
            JOIN position_classes pc ON p.id = pc.position_id
            WHERE pc.class_id = ?
        """, (class_id,)).fetchall()
    else:
        positions = conn.execute("SELECT id, base_name, quota, current_count, instructor, requirements FROM positions").fetchall()
    
    # 获取共享岗位（未指定班级的岗位）
    shared = conn.execute("""
        SELECT p.id, p.base_name, p.quota, p.current_count, p.instructor, p.requirements
        FROM positions p
        WHERE p.id NOT IN (SELECT DISTINCT position_id FROM position_classes)
    """).fetchall()
    
    # 获取当前学生的指定岗位ID
    my_assigned = set()
    if student_db_id:
        rows = conn.execute("SELECT position_id FROM student_position_assign WHERE student_id=?", (student_db_id,)).fetchall()
        my_assigned = set(r["position_id"] for r in rows)
    
    # 收集所有岗位（去重）
    all_positions_raw = {}
    for p in list(positions) + list(shared):
        if p["id"] not in all_positions_raw:
            all_positions_raw[p["id"]] = dict(p)
    
    # 获取所有岗位的指定人数（在关闭连接前完成）
    assigned_counts = {}
    for pid in all_positions_raw.keys():
        row = conn.execute("SELECT COUNT(*) as cnt FROM student_position_assign WHERE position_id=?", (pid,)).fetchone()
        assigned_counts[pid] = row["cnt"] if row else 0
    
    # 获取系统开放时间（北京时间）
    from datetime import datetime, timedelta
    open_time_str = get_setting("open_time", "")
    if open_time_str:
        try:
            open_dt = datetime.strptime(open_time_str, "%Y-%m-%dT%H:%M")
            now_beijing = datetime.now()
            open_minutes = (now_beijing - open_dt).total_seconds() / 60
        except ValueError:
            open_minutes = -1
    else:
        open_minutes = -1
    
    # 构建结果列表
    assigned_list = []
    normal_list = []
    
    for pid, p in all_positions_raw.items():
        assigned_cnt = assigned_counts.get(pid, 0)
        is_my = pid in my_assigned
        
        if is_my:
            # 指定学生看到原配额
            remaining = max(0, p["quota"] - p["current_count"])
        else:
            # 非指定学生：指定名额不预扣，指定学生已选/超时1分钟/被占位时才减少
            occupied_designated = 0
            if assigned_cnt > 0:
                designated_students = conn.execute(
                    "SELECT student_id FROM student_position_assign WHERE position_id=?", (pid,)
                ).fetchall()
                for ds in designated_students:
                    sub = conn.execute(
                        "SELECT id FROM submissions WHERE student_id=? AND position_id=?",
                        (ds["student_id"], pid)
                    ).fetchone()
                    if sub:
                        occupied_designated += 1
                    elif open_minutes >= 1:
                        occupied_designated += 1
                    else:
                        any_sub = conn.execute(
                            "SELECT id FROM submissions WHERE position_id=? AND student_id NOT IN (SELECT student_id FROM student_position_assign WHERE position_id=?)",
                            (pid, pid)
                        ).fetchone()
                        if any_sub:
                            occupied_designated += 1
            remaining = max(0, p["quota"] - occupied_designated - p["current_count"])
        
        is_selected = submitted_position_id == pid
        
        item = {
            "id": pid,
            "base_name": p["base_name"],
            "quota": p["quota"],
            "remaining": remaining,
            "instructor": p["instructor"],
            "requirements": p["requirements"],
            "assigned": is_my,
            "selected": is_selected
        }
        
        if is_my:
            assigned_list.append(item)
        else:
            normal_list.append(item)
    
    # 随机排序（不包括指定岗位）
    if random_order and student_db_id:
        import random
        random.Random(student_db_id).shuffle(normal_list)
    
    conn.close()
    return jsonify(assigned_list + normal_list)

@app.route("/api/student_positions/<int:student_id>")
def api_student_positions(student_id):
    """获取某学生可见的岗位（用于指定功能的岗位下拉筛选）"""
    conn = get_db()
    
    # 获取学生所在班级
    student = conn.execute("SELECT class_id FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        conn.close()
        return jsonify([])
    
    class_id = student["class_id"]
    if not class_id:
        # 学生未分班，显示所有岗位
        positions = conn.execute("SELECT id, base_name, quota, current_count FROM positions ORDER BY base_name").fetchall()
        conn.close()
        return jsonify([{"id": p["id"], "name": p["base_name"] + " (剩余" + str(p["quota"]-p["current_count"]) + "名)"} for p in positions])
    
    # 获取该班级可见的岗位
    positions = conn.execute("""
        SELECT p.id, p.base_name, p.quota, p.current_count
        FROM positions p
        JOIN position_classes pc ON p.id = pc.position_id
        WHERE pc.class_id = ?
    """, (class_id,)).fetchall()
    
    # 获取共享岗位
    shared = conn.execute("""
        SELECT id, base_name, quota, current_count
        FROM positions
        WHERE id NOT IN (SELECT DISTINCT position_id FROM position_classes)
    """).fetchall()
    
    conn.close()
    
    # 合并去重
    seen = set()
    result = []
    for p in list(positions) + list(shared):
        if p["id"] not in seen:
            seen.add(p["id"])
            result.append({"id": p["id"], "name": p["base_name"] + " (剩余" + str(p["quota"]-p["current_count"]) + "名)"})
    
    return jsonify(result)

@app.route("/api/progress/<int:class_id>")
def api_progress(class_id):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM students WHERE class_id=?", (class_id,)).fetchone()[0]
    submitted = conn.execute("SELECT COUNT(*) FROM students WHERE class_id=? AND has_submitted=1", (class_id,)).fetchone()[0]
    positions = conn.execute("""
        SELECT p.base_name, p.quota, p.current_count
        FROM positions p
        JOIN position_classes pc ON p.id = pc.position_id
        WHERE pc.class_id = ?
        ORDER BY p.base_name
    """, (class_id,)).fetchall()
    conn.close()
    return jsonify({
        "total": total,
        "submitted": submitted,
        "remaining": total - submitted,
        "positions": [{"base_name": p["base_name"], "quota": p["quota"], "current_count": p["current_count"]} for p in positions]
    })

# ========== Student Pages ==========
@app.route("/")
def index():
    return redirect(url_for("student_login"))

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    check_time_based_open()
    mode = get_system_mode()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sid = request.form.get("student_id", "").strip()
        conn = get_db()
        student = conn.execute("SELECT s.*, c.name as class_name FROM students s LEFT JOIN classes c ON s.class_id=c.id WHERE s.name=? AND s.student_id=?", (name, sid)).fetchone()
        conn.close()
        if student:
            session["student_id"] = student["id"]
            session["student_name"] = student["name"]
            session["student_sid"] = student["student_id"]
            session["class_id"] = student["class_id"]
            session["class_name"] = student["class_name"]
            if student["has_submitted"]:
                session.clear()
                flash("你已完成岗位选择", "info")
                return redirect(url_for("student_login"))
            if mode == "close":
                flash("系统暂未开放", "warning")
                return redirect(url_for("student_login"))
            return redirect(url_for("student_select"))
        flash("姓名或学号不正确", "danger")
    return render_template("student_login.html", system_mode=mode)

@app.route("/student/select", methods=["GET", "POST"])
def student_select():
    if "student_id" not in session:
        return redirect(url_for("student_login"))
    check_time_based_open()
    mode = get_system_mode()
    if mode == "close":
        flash("系统暂未开放", "warning")
        return redirect(url_for("student_login"))
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
    if student["has_submitted"]:
        conn.close()
        return redirect(url_for("student_result"))
    assigned = conn.execute("""
        SELECT p.* FROM student_position_assign spa
        JOIN positions p ON spa.position_id=p.id
        WHERE spa.student_id=?
    """, (session["student_id"],)).fetchone()
    conn.close()
    if request.method == "POST":
        if mode != "open":
            flash("当前为预览模式，暂不能选择", "warning")
            return redirect(url_for("student_select"))
        pid = request.form.get("position_id")
        if not pid:
            flash("请选择一个岗位", "danger")
            return redirect(url_for("student_select"))
        pid = int(pid)
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            pos = conn.execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()
            if not pos:
                conn.rollback()
                flash("岗位不存在", "danger")
                conn.close()
                return redirect(url_for("student_select"))
            # 检查是否是当前学生的指定岗位
            is_my_assigned = conn.execute(
                "SELECT 1 FROM student_position_assign WHERE position_id=? AND student_id=?",
                (pid, session["student_id"])
            ).fetchone()
            # 计算该岗位被多少人指定
            assigned_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM student_position_assign WHERE position_id=?",
                (pid,)
            ).fetchone()["cnt"]
            if is_my_assigned:
                # 指定学生有专属名额，检查是否还有空位
                if pos["current_count"] >= pos["quota"]:
                    conn.rollback()
                    flash("该岗位名额已满", "danger")
                    conn.close()
                    return redirect(url_for("student_select"))
            else:
                # 非指定学生：有效配额 = 原配额 - 指定人数
                effective_quota = max(0, pos["quota"] - assigned_count)
                if pos["current_count"] >= effective_quota:
                    conn.rollback()
                    flash("该岗位名额已满，请选择其他岗位", "danger")
                    conn.close()
                    return redirect(url_for("student_select"))
            conn.execute("UPDATE positions SET current_count=current_count+1 WHERE id=? AND current_count<quota", (pid,))
            conn.execute("INSERT INTO submissions (student_id, position_id) VALUES (?, ?)",
                        (session["student_id"], pid))
            conn.execute("UPDATE students SET has_submitted=1, submitted_at=datetime('now','localtime'), assigned_position_id=? WHERE id=?",
                        (pid, session["student_id"]))
            conn.commit()
            conn.close()
            return redirect(url_for("student_result"))
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f"选择失败: {e}", "danger")
            return redirect(url_for("student_select"))
    return render_template("student_select.html",
                           student_id=session.get("student_id"),
                           class_id=session.get("class_id"),
                           class_name=session.get("class_name"),
                           student_name=session.get("student_name"),
                           system_mode=mode)

@app.route("/student/result")
def student_result():
    if "student_id" not in session:
        return redirect(url_for("student_login"))
    conn = get_db()
    sub = conn.execute("""
        SELECT p.base_name, p.instructor, p.requirements, sub.created_at
        FROM submissions sub JOIN positions p ON sub.position_id=p.id
        WHERE sub.student_id=?
    """, (session["student_id"],)).fetchone()
    conn.close()
    if not sub:
        return redirect(url_for("student_login"))
    return render_template("student_result.html", sub=sub,
                           student_name=session.get("student_name"),
                           class_name=session.get("class_name"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)












