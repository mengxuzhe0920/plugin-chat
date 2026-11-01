package run.halo.chat;

import org.pf4j.PluginWrapper;
import run.halo.app.plugin.BasePlugin;

/**
 * 小窝聊天 UC 入口插件。
 * 全部能力在前端 UI（ucRoutes 注册侧边栏菜单 + iframe 内嵌 /chat/），
 * 后端不做任何事，仅作为插件载体存在。
 */
public class ChatPlugin extends BasePlugin {

    public ChatPlugin(PluginWrapper wrapper) {
        super(wrapper);
    }

    @Override
    public void start() {
        // nothing to do
    }

    @Override
    public void stop() {
        // nothing to do
    }
}
