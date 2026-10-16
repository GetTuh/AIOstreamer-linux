local utils = require "mp.utils"

local function uosc(command)
    mp.commandv("script-binding", "uosc/" .. command)
end

local trickplay = false
local pending = nil
local commit_timer = nil
local SCRUB_COMMIT_S = 0.8

mp.register_script_message("jftv-trickplay", function(width)
    trickplay = (tonumber(width) or 0) > 0
end)

local function commit()
    if pending then
        mp.commandv("seek", tostring(pending), "absolute")
        pending = nil
        mp.commandv("script-message-to", "thumbfast", "clear")
    end
end

local function seek(seconds)
    if not trickplay then
        mp.commandv("seek", tostring(seconds))
        uosc("flash-timeline")
        return
    end
    local duration = mp.get_property_number("duration") or 0
    local base = pending or mp.get_property_number("time-pos") or 0
    pending = math.max(0, math.min(duration > 0 and duration - 1 or base + seconds, base + seconds))
    uosc("flash-timeline")
    mp.commandv("script-message-to", "thumbfast", "jftv-scrub", tostring(pending))
    if commit_timer then
        commit_timer:kill()
    end
    commit_timer = mp.add_timeout(SCRUB_COMMIT_S, commit)
end

mp.register_event("end-file", function()
    pending = nil
    trickplay = false
end)

local function toggle_pause()
    if pending then
        if commit_timer then
            commit_timer:kill()
        end
        commit()
        return
    end
    mp.command("cycle pause")
    uosc("flash-timeline")
end

local versions = {}

mp.register_script_message("jftv-versions", function(json)
    versions = utils.parse_json(json) or {}
end)

local function version_items()
    local items = {}
    for _, version in ipairs(versions) do
        items[#items + 1] = {
            title = version.title,
            hint = version.hint,
            value = { "script-message", "jftv-version", version.id },
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

local function menu()
    local items = {
        { title = "Audio", items = track_items("audio", "aid", false) },
        { title = "Subtitles", items = track_items("sub", "sid", true) },
    }
    if #versions > 1 then
        items[#items + 1] = { title = "Version", items = version_items() }
    end
    if (mp.get_property_number("chapters") or 0) > 0 then
        items[#items + 1] = { title = "Chapters", value = "script-binding uosc/chapters" }
    end
    items[#items + 1] = { title = "Stop playback", value = "quit" }
    mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json({ type = "jftv-playback", title = "Playback", items = items }))
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
if mp.get_opt("jftv-overlay") ~= "no" then
    for _, binding in ipairs(bindings) do
        mp.add_key_binding(binding[1], "jftv-" .. binding[1], binding[2], { repeatable = binding[3] or false })
    end
end

for _, key in ipairs({ "ESC", "GO_BACK", "MBTN_BACK", "BS" }) do
    mp.add_key_binding(key, "jftv-back-" .. key, function() mp.command("quit") end)
end
