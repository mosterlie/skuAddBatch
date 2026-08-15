tell application "Google Chrome"
    repeat with w in windows
        set u to URL of active tab of w
        if u does not contain "127.0.0.1" and u does not contain "localhost" then
            return u
        end if
    end repeat
end tell
