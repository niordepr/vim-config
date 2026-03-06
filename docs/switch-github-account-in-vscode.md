# 在 VSCode 中切换 GitHub 账号并处理 Copilot 聊天记录

## 一、在 VSCode 中切换 GitHub 账号

### 步骤 1：登出当前 GitHub 账号

1. 点击 VSCode 左下角的 **账户图标**（头像）。
2. 在弹出的菜单中，找到已登录的 GitHub 账号，点击 **Sign Out（登出）**。

或者通过命令面板操作：

1. 按 `Ctrl+Shift+P`（macOS: `Cmd+Shift+P`）打开命令面板。
2. 输入 `Sign Out`，选择 **GitHub: Sign Out**。

### 步骤 2：清除旧的凭据（如有必要）

如果登出后仍然使用旧账号，需要手动清除系统中存储的凭据：

- **Windows**：打开 **控制面板 > 凭据管理器 > Windows 凭据**，找到并删除与 `github.com` 相关的条目。
- **macOS**：打开 **钥匙串访问（Keychain Access）**，搜索 `github.com`，删除相关条目。
- **Linux**：如果使用 `git-credential-store`，编辑 `~/.git-credentials` 文件，删除旧的 GitHub 条目。如果使用 `libsecret` 或 `gnome-keyring`，通过相应的密钥管理工具删除。

### 步骤 3：登录新的 GitHub 账号

1. 点击 VSCode 左下角的 **账户图标**。
2. 选择 **Sign in with GitHub（使用 GitHub 登录）**。
3. 浏览器会打开 GitHub 授权页面，使用新账号登录并授权。

### 步骤 4：验证登录状态

1. 再次点击 VSCode 左下角的 **账户图标**，确认显示的是新账号。
2. 如果使用 GitHub Copilot，确认 Copilot 图标在状态栏中显示为已激活状态。

## 二、更新 Git 全局配置

切换 GitHub 账号后，建议同时更新本地 Git 配置：

```bash
git config --global user.name "你的新用户名"
git config --global user.email "你的新邮箱@example.com"
```

如果只想修改某个项目的配置，可以在项目目录中去掉 `--global`：

```bash
git config user.name "你的新用户名"
git config user.email "你的新邮箱@example.com"
```

## 三、关于 Copilot 聊天记录

### 聊天记录存储在本地

GitHub Copilot Chat 的聊天记录**存储在本地 VSCode 的工作区存储中**，而不是绑定到 GitHub 账号。因此：

- **切换账号后，本地的聊天记录通常仍然保留**，不会因为更换账号而丢失。
- 聊天记录与 VSCode 的工作区（workspace）关联，只要你使用同一个 VSCode 工作区，历史记录就还在。

### 聊天记录的存储位置

Copilot Chat 的历史记录存储在 VSCode 的用户数据目录中：

- **Windows**：`%APPDATA%\Code\User\workspaceStorage\`
- **macOS**：`~/Library/Application Support/Code/User/workspaceStorage/`
- **Linux**：`~/.config/Code/User/workspaceStorage/`

每个工作区对应一个带有哈希值的子目录，其中包含 Copilot Chat 的历史数据。

### 如果需要备份聊天记录

如果你担心切换账号会影响聊天记录，可以在切换前备份：

1. 关闭 VSCode。
2. 复制上述路径下的 `workspaceStorage` 文件夹作为备份。
3. 切换账号后，如果记录丢失，可以将备份还原。

### 跨设备同步聊天记录

如果你需要在不同设备间同步聊天记录，可以使用 VSCode 的 **Settings Sync（设置同步）** 功能：

1. 按 `Ctrl+Shift+P`（macOS: `Cmd+Shift+P`）打开命令面板。
2. 输入 `Settings Sync: Turn On`，开启设置同步。
3. 选择使用新的 GitHub 账号登录同步。

> **注意**：Settings Sync 同步的内容包括设置、快捷键、扩展等，但**聊天记录可能不在同步范围内**。如需完整迁移，建议使用手动备份的方式。

## 四、常见问题

### Q：切换账号后 Copilot 不工作了？

确保新账号拥有有效的 GitHub Copilot 订阅。可以在 [GitHub Copilot 设置页面](https://github.com/settings/copilot) 检查订阅状态。

### Q：切换账号后聊天记录消失了？

1. 检查你是否在同一个 VSCode 工作区中。
2. 检查 `workspaceStorage` 目录中的数据是否还在。
3. 如果有备份，尝试还原备份文件。

### Q：如何在 VSCode 中同时使用多个 GitHub 账号？

VSCode 原生不支持同时登录多个 GitHub 账号。但可以通过以下方式实现：

- 使用不同的 VSCode 配置文件（Profile）来关联不同的 GitHub 账号。
- 在命令面板中使用 `Profiles: Create Profile` 创建新的配置文件，然后在不同配置文件中登录不同的账号。
