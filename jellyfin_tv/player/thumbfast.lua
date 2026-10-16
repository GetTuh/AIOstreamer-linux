local utils = require "mp.utils"

local OVERLAY_ID = 42
local size = { width = 0, height = 0 }
local wanted = nil
local shown = false
local label = mp.create_osd_overlay("ass-events")

local function scale()
    local dims = mp.get_property_native("osd-dimensions") or {}
    local h = dims.h or 1080
    return math.max(h / 1080, 0.5) * 1.5, dims.w or 1920, h
end

local function publish()
    local factor = scale()
    local info = { width = math.floor(size.width * factor), height = math.floor(size.height * factor), disabled = size.width == 0, available = size.width > 0 }
    mp.commandv("script-message", "thumbfast-info", utils.format_json(info))
end

local function clear()
    wanted = nil
    if shown then
        mp.command_native({ "overlay-remove", OVERLAY_ID })
        shown = false
    end
    label:remove()
end

local function request(seconds, x, y)
    if size.width == 0 then
        return
    end
    wanted = { seconds = tostring(seconds), x = math.floor(tonumber(x)), y = math.floor(tonumber(y)) }
    mp.commandv("script-message", "jftv-thumb", wanted.seconds)
end

local function format_time(seconds)
    seconds = math.floor(seconds)
    local h, m, s = math.floor(seconds / 3600), math.floor(seconds / 60) % 60, seconds % 60
    return h > 0 and string.format("%d:%02d:%02d", h, m, s) or string.format("%d:%02d", m, s)
end

mp.register_script_message("jftv-trickplay", function(width, height)
    clear()
    size.width, size.height = tonumber(width) or 0, tonumber(height) or 0
    publish()
end)

mp.register_script_message("thumb", request)
mp.register_script_message("clear", clear)

mp.register_script_message("jftv-scrub", function(seconds)
    local factor, w, h = scale()
    local duration = mp.get_property_number("duration") or 0
    local t = tonumber(seconds) or 0
    local tw, th = size.width * factor, size.height * factor
    local x = duration > 0 and (t / duration) * w - tw / 2 or (w - tw) / 2
    x = math.max(24, math.min(w - tw - 24, x))
    local y = h * 0.86 - th
    request(t, x, y)
    label.res_x, label.res_y = w, h
    label.data = string.format("{\\an2\\pos(%d,%d)\\fs%d\\b1\\bord2\\3c&H000000&\\1c&HFFFFFF&}%s", x + tw / 2, y - 8, math.floor(44 * h / 1080), format_time(t))
    label:update()
end)

mp.register_script_message("jftv-thumb-ready", function(seconds, path, width, height)
    if not wanted or wanted.seconds ~= seconds then
        return
    end
    local factor = scale()
    local w, h = tonumber(width), tonumber(height)
    mp.command_native({ "overlay-add", OVERLAY_ID, wanted.x, wanted.y, path, 0, "bgra", w, h, w * 4, math.floor(w * factor), math.floor(h * factor) })
    shown = true
end)

mp.observe_property("osd-dimensions", "native", function()
    if size.width > 0 then
        publish()
    end
end)
mp.register_event("end-file", clear)
