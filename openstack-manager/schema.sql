-- 添加分组表
CREATE TABLE IF NOT EXISTS ssh_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 修改连接表，添加分组关联
ALTER TABLE ssh_connections ADD COLUMN group_name TEXT DEFAULT 'default' REFERENCES ssh_groups(name); 