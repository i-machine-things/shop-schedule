sub init()
    m.contentGroup = m.top.findNode("contentGroup")
    m.eggPresses = 0
    m.eggLastPress = 0
    sec = CreateObject("roRegistrySection", "ScheduleConfig")

    if sec.Exists("serverUrl") and sec.Read("serverUrl") <> "" then
        showSchedule()
    else
        showSetup()
    end if
end sub

' Undocumented: mash "rewind" 5x within 2s of each other, from anywhere in the
' app, for a small credit. See CODING_NOTES.md "Easter Eggs". Kept low-key on
' purpose — this runs on a shop floor TV, not a home-theater device.
function onKeyEvent(key as String, press as Boolean) as Boolean
    if press and key = "rewind" then
        now = CreateObject("roDateTime").AsSeconds()
        if now - m.eggLastPress > 2 then m.eggPresses = 0
        m.eggLastPress = now
        m.eggPresses = m.eggPresses + 1
        if m.eggPresses >= 5 then
            m.eggPresses = 0
            showEasterEgg()
            return true
        end if
    end if
    return false
end function

sub showEasterEgg()
    dialog = CreateObject("roSGNode", "Dialog")
    dialog.title = "Shop Schedule"
    dialog.message = "Built on the shop floor. Back to work."
    dialog.buttons = ["Nice"]
    dialog.observeField("buttonSelected", "onEasterEggDismissed")
    m.top.dialog = dialog
end sub

sub onEasterEggDismissed()
    m.top.dialog.close = true
end sub

sub showSetup()
    m.contentGroup.removeChildren(m.contentGroup.getChildren(-1, 0))
    m.setupView = CreateObject("roSGNode", "SetupScreen")
    m.setupView.observeField("setupComplete", "onSetupComplete")
    m.contentGroup.appendChild(m.setupView)
    ' screenShown() (not setFocus() here) — init() runs during CreateObject(), before
    ' appendChild above attaches the node to the live tree, and Roku's focus manager
    ' doesn't reliably honor setFocus() on an unattached node.
    m.setupView.callFunc("screenShown")
end sub

sub showSchedule()
    m.contentGroup.removeChildren(m.contentGroup.getChildren(-1, 0))
    m.scheduleView = CreateObject("roSGNode", "ScheduleScreen")
    m.scheduleView.observeField("reconfigure", "onReconfigure")
    m.contentGroup.appendChild(m.scheduleView)
    m.scheduleView.callFunc("screenShown")
end sub

sub onReconfigure()
    sec = CreateObject("roRegistrySection", "ScheduleConfig")
    sec.Delete("serverUrl")
    sec.Flush()
    showSetup()
end sub

sub onSetupComplete()
    showSchedule()
end sub
