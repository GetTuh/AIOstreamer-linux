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
    items[#items + 1] = { title = "Stop playback", value = "quit" }
    mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json({ type = "aios-playback", title = "Playback", items = items }))
end

local bindings = {
    { "LEFT", function() seek(-10) end, true },
    { "RIGHT", function() seek(10) end, true },
    { "ENTER", toggle_pause },
    { "KP_ENTER", toggle_pause },
    { "UP", menu },
    { "MENU", menu },
    { "DOWN", function() uosc("flash-ui") end },
}
if mp.get_opt("aios-overlay") ~= "no" then
    for _, binding in ipairs(bindings) do
        mp.add_key_binding(binding[1], "aios-" .. binding[1], binding[2], { repeatable = binding[3] or false })
    end
end

for _, key in ipairs({ "ESC", "GO_BACK", "MBTN_BACK", "BS" }) do
    mp.add_key_binding(key, "aios-back-" .. key, function() mp.command("quit") end)
end
