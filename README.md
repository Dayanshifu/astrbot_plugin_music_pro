# AstrBot 高级点歌

AstrBot点歌插件，智能使用多个api，达成免费听各种音乐

**修改自[astrbot_plugin_qymusic](https://github.com/pmh1314520/astrbot_plugin_qymusic)，[netease-music-astrbot-plugin](https://github.com/NachoCrazy/netease-music-astrbot-plugin)**

## 安装与配置

### 依赖

#### 通过公开的项目获取音源

如果你不想搭建服务器，又不能使用默认的服务，使用一些公开的项目

以下是目前搜索到的一些服务：
```
https://163api.qijieya.cn/
https://zm.armoe.cn/
https://wyy.xhily.com/
```

请在插件配置中`NeteaseCloudMusicApi 服务地址`一项中填入音源链接

#### 部署自己的项目

本插件依赖一个外部的 **Netease Cloud Music API (增强版)** 服务。请您务必先根据其文档自行部署该服务。

- **API 仓库地址**: [https://github.com/neteasecloudmusicapienhanced/api-enhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced)

推荐的部署方式是使用 Docker。


## 使用方法

```
/点歌 青花
```
在机器人返回搜索列表后，想听的歌对应的**数字**即可。
