package run.halo.app.plugin;

import org.pf4j.Plugin;
import org.pf4j.PluginWrapper;

/**
 * 编译用 stub：真实类由 Halo 主程序在运行时提供。
 */
public abstract class BasePlugin extends Plugin {
    public BasePlugin() {
        super();
    }

    public BasePlugin(PluginWrapper wrapper) {
        super(wrapper);
    }
}
