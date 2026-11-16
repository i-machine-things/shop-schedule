sub init()
    m.urlFieldBg = m.top.findNode("urlFieldBg")
    m.urlFieldLabel = m.top.findNode("urlFieldLabel")
    m.saveButtonBg = m.top.findNode("saveButtonBg")
    m.saveButtonLabel = m.top.findNode("saveButtonLabel")
    m.statusLabel = m.top.findNode("statusLabel")

    m.urlValue = ""
    m.focusIndex = 0
    updateFocusVisual()
end sub

sub screenShown()
    m.top.setFocus(true)
end sub

' Rows: 0 = url field, 1 = save button. Plain Rectangles have no built-in focus
' ring, so focus is tracked manually and shown via a border-color swap.
sub updateFocusVisual()
    focusedColor = "0x4AAFFFFF"
    unfocusedUrlColor = "0x0D1A2BFF"
    unfocusedSaveColor = "0x1A6640FF"

    if m.focusIndex = 0 then
        m.urlFieldBg.color = focusedColor
        m.saveButtonBg.color = unfocusedSaveColor
    else
        m.urlFieldBg.color = unfocusedUrlColor
        m.saveButtonBg.color = focusedColor
    end if
end sub

function onKeyEvent(key as String, press as Boolean) as Boolean
    if not press then return false

    if key = "up" and m.focusIndex = 1 then
        m.focusIndex = 0
        updateFocusVisual()
        return true
    else if key = "down" and m.focusIndex = 0 then
        m.focusIndex = 1
        updateFocusVisual()
        return true
    else if key = "OK" then
        if m.focusIndex = 0 then
            openUrlKeyboard()
        else
            onSavePressed()
        end if
        return true
    end if
    return false
end function

sub openUrlKeyboard()
    dialog = CreateObject("roSGNode", "KeyboardDialog")
    dialog.title = "Server Address"
    dialog.buttons = ["OK", "Cancel"]
    if m.urlValue <> "" then dialog.keyboard.text = m.urlValue
    dialog.observeField("buttonSelected", "onUrlKeyboardClosed")
    m.urlDialog = dialog
    m.top.getScene().dialog = dialog
end sub

sub onUrlKeyboardClosed()
    if m.urlDialog.buttonSelected = 0 then
        text = m.urlDialog.keyboard.text
        if text <> invalid and text.Trim() <> "" then
            m.urlValue = text.Trim()
            m.urlFieldLabel.text = m.urlValue
            m.urlFieldLabel.color = "0x4AAFFFFF"
            m.statusLabel.text = ""
        end if
    end if
    m.urlDialog.close = true
end sub

sub onSavePressed()
    if m.urlValue = "" then
        m.statusLabel.text = "Enter a server address first."
        return
    end if

    url = normalizeUrl(m.urlValue)

    sec = CreateObject("roRegistrySection", "ScheduleConfig")
    sec.Write("serverUrl", url)
    sec.Flush()

    m.top.setupComplete = true
end sub

' Prepends http:// if no scheme was typed (this is an internal LAN kiosk --
' plain http is the expected case, not https), and strips a trailing slash
' so URL-building elsewhere can always do serverUrl + "/path" unambiguously.
function normalizeUrl(raw as String) as String
    url = raw
    if not (url.InStr(0, "://") >= 0) then
        url = "http://" + url
    end if
    if url.Len() > 0 and url.Right(1) = "/" then
        url = url.Left(url.Len() - 1)
    end if
    return url
end function
