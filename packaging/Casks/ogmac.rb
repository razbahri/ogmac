cask "ogmac" do
  version "0.2.0"
  sha256 :no_check

  url "https://github.com/razbahri/ogmac/releases/download/v#{version}/Ogmac.app.zip"
  name "ogmac"
  desc "Outlook to Google Calendar one-way sync — menu bar app"
  homepage "https://github.com/razbahri/ogmac"

  depends_on macos: ">= :sonoma"

  app "Ogmac.app"

  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-d", "com.apple.quarantine", "#{appdir}/Ogmac.app"],
                   sudo: false
  end

  zap trash: [
    "~/Library/Preferences/com.ogmac.app.plist",
  ]
end
