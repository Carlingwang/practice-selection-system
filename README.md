# 实习选岗系统

多项目实习岗位选择系统，支持创建多个独立的填报/选择项目。

## 功能特性

### 多项目管理
- 创建多个独立项目（导师选择、岗位选择、投票活动等）
- 每个项目拥有独立的数据空间，互不干扰
- 项目的创建、编辑、删除和状态管理

### 管理端
- 班级管理（增删改）
- 学生管理（Excel批量导入、单条增删、批量删除）
- 岗位管理（增删改、Excel批量导入、配额设置）
- 指定关系管理（为指定学生分配指定岗位）
- 实时看板（各岗位已选人数/总配额）
- 定时控制（设置开放/关闭时间段 + 倒计时）
- 排序控制（顺序/随机展示）
- 结果导出（Excel）

### 学生端
- 选择项目 → 输入姓名学号登录
- 问卷星风格UI（渐变背景、卡片式岗位）
- 实时轮询各岗位剩余名额
- 指定学生优先显示指定岗位

### 配额逻辑
- 指定学生看到完整配额
- 非指定学生看到动态计算的剩余名额
- 指定学生选指定岗位不受配额限制

## 快速部署

```bash
# 克隆项目
git clone https://github.com/Carlingwang/practice-selection-system.git
cd practice-selection-system

# 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 初始化数据库
python -c "from models import init_db; init_db()"

# 启动服务
gunicorn -c gunicorn_config.py app:app
```

## 一键部署脚本

```bash
chmod +x deploy.sh
./deploy.sh
```

## 管理员账号

- 用户名：`kayson`
- 密码：`Wenjuan13579@`

## 访问地址

| 入口 | 地址 |
|------|------|
| 学生入口 | `/student/login` |
| 管理后台 | `/admin/login` |

## 技术栈

- 后端：Python Flask
- 数据库：SQLite
- 前端：Jinja2 + Bootstrap 5
- 部署：Gunicorn + Nginx

## 数据导入

### 学生导入模板（Excel）
| 姓名 | 学号 |
|------|------|
| 张三 | 2021001 |

### 岗位导入模板（Excel）
| 实习基地 | 配额人数 | 指导教师 | 备注要求 | 可见班级(逗号分隔) |
|----------|----------|----------|----------|-------------------|
| XX医院 | 5 | 张老师 | 需持护士证 | 护理1班,护理2班 |

### 指定关系导入模板（Excel）
| 学号 | 岗位名称 |
|------|----------|
| 2021001 | XX医院 |

## 项目结构

```
practice-selection-system/
├── app.py              # Flask应用主文件
├── models.py           # 数据库模型
├── requirements.txt    # Python依赖
├── gunicorn_config.py  # Gunicorn配置
├── deploy.sh           # 一键部署脚本
├── init_db.sql         # 干净数据库初始化
└── templates/          # HTML模板
    ├── base.html
    ├── admin_base.html
    ├── admin_login.html
    ├── admin_projects.html    # 项目列表
    ├── admin_dashboard.html   # 项目看板
    ├── admin_classes.html
    ├── admin_students.html
    ├── admin_positions.html
    ├── admin_assign.html
    ├── admin_submissions.html
    ├── student_login.html     # 含项目选择
    ├── student_select.html    # 问卷星风格
    └── student_result.html
```
