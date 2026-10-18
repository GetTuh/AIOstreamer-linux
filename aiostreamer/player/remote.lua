local utils = require "mp.utils"

local function uosc(command)
    mp.commandv("script-binding", "uosc/" .. command)
end

local function seek(seconds)
    mp.commandv("seek", tostring(seconds))
    uosc("flash-timeline")
end

local function toggle_pause()
    mp.command("cycle pause")
    uosc("flash-timeline")
end

local versions = {}

mp.register_script_message("aios-versions", function(json)
    versions = utils.parse_json(json) or {}
end)

local function version_items()
    local items = {}
    for _, version in ipairs(versions) do
        items[#items + 1] = {
            title = version.title,
            hint = version.hint,
            value = { "script-message", "aios-version", version.id },
            active = version.active,
        }
    end
    return items
end

local CHANNELS = { [1] = "1.0", [2] = "2.0", [6] = "5.1", [8] = "7.1" }

local function track_title(track)
    local parts = {}
    if track.lang then
        parts[#parts + 1] = track.lang:upper()
    end
    if track.title and track.title ~= "" then
        parts[#parts + 1] = track.title
    end
    if #parts == 0 then
        parts[1] = "Track " .. track.id
    end
    return table.concat(parts, " · ")
end

local function track_hint(track)
    local parts = {}
    if track.codec then
        parts[#parts + 1] = track.codec:upper()
    end
    local channels = track["demux-channel-count"]
    if channels then
        parts[#parts + 1] = CHANNELS[channels] or (channels .. "ch")
    end
    if track.forced then
        parts[#parts + 1] = "forced"
    end
    if track.external then
        parts[#parts + 1] = "external"
    end
    return table.concat(parts, " · ")
end

local function track_items(kind, property, allow_off)
    local items = {}
    local any_selected = false
    for _, track in ipairs(mp.get_property_native("track-list") or {}) do
        if track.type == kind then
            any_selected = any_selected or track.selected
            items[#items + 1] = {
                title = track_title(track),
                hint = track_hint(track),
                value = { "set", property, tostring(track.id) },
                active = track.selected,
            }
        end
    end
    if allow_off then
        table.insert(items, 1, { title = "Off", value = { "set", property, "no" }, active = not any_selected })
    end
    return items
end

local function subtitle_items()
    local items = track_items("sub", "sid", true)
    items[#items + 1] = { title = "Get more subtitles", hint = "search again", value = { "script-message", "aios-more-subs" } }
    return items
end

local function menu()
    local items = {
        { title = "Audio", items = track_items("audio", "aid", false) },
        { title = "Subtitles", items = subtitle_items() },
    }
    if #versions > 1 then
        items[#items + 1] = { title = "Version", items = version_items() }
    end
    if (mp.get_property_number("chapters") or 0) > 0 then
        items[#items + 1] = { title = "Chapters", value = "script-binding uosc/chapters" }
    end
    items[#items + 1] = { title = "Keys", value = { "script-message-to", "remote", "aios-keys" } }
    items[#items + 1] = { title = "Stop playback", value = "quit" }
    mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json({ type = "aios-playback", title = "Playback", items = items }))
end

local function keys_file()
    local path = mp.get_opt("aios-keys")
    local file = path and io.open(path, "r")
    if not file then
        return {}
    end
    local data = utils.parse_json(file:read("*a")) or {}
    file:close()
    return data
end

local keys = keys_file()
local overlay = mp.get_opt("aios-overlay") ~= "no"

local function legend()
    if overlay then
        mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json({ type = "aios-keys", title = "Keys", items = keys.legend or {} }))
        return
    end
    local lines = {}
    for _, entry in ipairs(keys.legend or {}) do
        lines[#lines + 1] = entry.title .. ": " .. entry.hint
    end
    mp.commandv("show-text", table.concat(lines, "\n"), "8000")
end

mp.register_script_message("aios-keys", legend)

local actions = {
    play_pause = { toggle_pause },
    seek_back = { function() seek(-10) end, true },
    seek_forward = { function() seek(10) end, true },
    menu = { menu, false, true },
    show_ui = { function() uosc("flash-ui") end, false, true },
    stop = { function() mp.command("quit") end },
    fullscreen = { function() mp.command("cycle fullscreen") end },
    mute = { function() mp.command("cycle mute") end },
    volume_up = { function() mp.command("add volume 2") end, true },
    volume_down = { function() mp.command("add volume -2") end, true },
    subtitles = { function() mp.command("cycle sub") end },
    audio = { function() mp.command("cycle audio") end },
    keys = { legend },
}
local always = { stop = true, keys = true }
local custom = {}
for _, action in ipairs(keys.custom or {}) do
    custom[action] = true
end

local defaults = {
    play_pause = { "ENTER", "KP_ENTER" },
    seek_back = { "LEFT" },
    seek_forward = { "RIGHT" },
    menu = { "UP", "MENU" },
    show_ui = { "DOWN" },
    stop = { "ESC", "GO_BACK", "MBTN_BACK", "BS" },
    keys = { "F1", "?" },
}

for action, spec in pairs(actions) do
    local enabled = overlay or always[action] or custom[action]
    if enabled and (overlay or not spec[3]) then
        for _, key in ipairs((keys.bindings or {})[action] or defaults[action] or {}) do
            mp.add_key_binding(key, "aios-" .. action .. "-" .. key, spec[1], { repeatable = spec[2] or false })
        end
    end
end
