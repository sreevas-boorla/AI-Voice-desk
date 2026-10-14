import os
import sys
import time
from playwright.sync_api import sync_playwright, expect

FRONTEND_URL = "http://localhost:5180"

def test_text_booking_flow(page):
    print("\n--- Testing Text Booking Flow ---")
    page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)
    expect(page).to_have_title("VoiceDesk — CareBridge Clinic AI Receptionist")

    # 1. Switch to Text Chat Mode
    text_mode_btn = page.locator("button:has-text('Text Chat Mode')")
    text_mode_btn.click()
    print("Switched to Text Chat Mode.")

    # 2. Enter booking request
    chat_input = page.locator("form input[type='text']")
    chat_input.fill("Book an appointment with Dr. Aisha Rao for tomorrow at 10 AM for patient Priya Nair, phone 9876543210")
    page.locator("button[type='submit']:has-text('Send')").click()
    print("Submitted booking request.")

    # 3. Wait for confirmation card to render
    page.wait_for_selector("text=BOOK Request", timeout=15000)
    print("Pending booking confirmation card displayed.")
    expect(page.locator("text=Dr. Aisha Rao").first).to_be_visible()
    expect(page.locator("button:has-text('Confirm & Persist')").first).to_be_visible()

    # 4. Click Confirm & Persist
    confirm_btn = page.locator("button:has-text('Confirm & Persist')").first
    confirm_btn.click()
    print("Clicked Confirm & Persist.")

    # 5. Wait for confirmed appointment response
    page.wait_for_selector("text=Appointment successfully booked with reference", timeout=15000)
    print("Received appointment confirmation message with reference.")
    expect(page.locator("text=Appointment successfully booked with reference").first).to_be_visible()

    # 6. Verify in Admin Portal
    page.locator("button:has-text('Admin Portal')").click()
    if page.locator("input[type='password']").is_visible():
        page.locator("form input[type='text']").fill("admin")
        page.locator("input[type='password']").fill("CareBridge2026!")
        page.locator("button:has-text('Sign In to Dashboard')").click()

    page.wait_for_selector("text=Clinic Administration Dashboard", timeout=15000)
    print("Navigated to Admin Portal.")
    
    # Check that the new booking appears in the appointments table with CONFIRMED status
    patient_row = page.locator("tr:has-text('9876543210')")
    expect(patient_row.first).to_be_visible()
    expect(patient_row.first.locator("text=CONFIRMED")).to_be_visible()
    print("Verified new appointment for 9876543210 appears in Admin Portal table with status CONFIRMED.")


def test_browser_microphone_and_spoken_responses(page):
    print("\n--- Testing Browser Speech Fallback (MOCKED Web Speech API in Headless Browser) ---")
    print("  [DISCLOSURE: This test exercises frontend speech event hooks, React state transitions,")
    print("   and audio DOM elements via a synthetic SpeechRecognition / SpeechSynthesis spy.")
    print("   It does NOT prove physical microphone hardware capture or acoustic loudspeaker playback.]")

    # 1. Inject Web Speech API mock/spy so headless Chromium can simulate SpeechRecognition and capture SpeechSynthesis
    page.add_init_script("""
    window.__spokenUtterances = [];
    
    class MockSpeechRecognition {
      constructor() {
        this.continuous = true;
        this.interimResults = false;
        this.lang = 'en-IN';
        this.onstart = null;
        this.onresult = null;
        this.onerror = null;
        this.onend = null;
        window.__mockRecognitionInstance = this;
      }
      start() {
        window.__recognitionStarted = true;
        if (this.onstart) setTimeout(() => this.onstart(), 50);
      }
      stop() {
        window.__recognitionStarted = false;
        if (this.onend) setTimeout(() => this.onend(), 50);
      }
      abort() {
        window.__recognitionStarted = false;
        if (this.onend) setTimeout(() => this.onend(), 50);
      }
      simulateVoiceInput(transcript) {
        if (this.onresult) {
          const event = {
            results: [
              [{ transcript: transcript }]
            ]
          };
          this.onresult(event);
        }
      }
    }
    
    window.webkitSpeechRecognition = MockSpeechRecognition;
    window.SpeechRecognition = MockSpeechRecognition;

    // Spy on SpeechSynthesis
    window.speechSynthesis.speak = function(utterance) {
      window.__spokenUtterances.push(utterance.text);
      if (utterance.onstart) setTimeout(() => utterance.onstart(), 20);
      if (utterance.onend) setTimeout(() => utterance.onend(), 200);
    };
    """)

    page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)

    # Verify initial page is in Voice Mode
    expect(page.locator("text=Receptionist Audio Channel").first).to_be_visible()
    expect(page.locator("text=Ready / Standby").first).to_be_visible()

    # Ensure Browser Web Speech engine is selected
    browser_engine_btn = page.locator("button:has-text('Browser Web Speech')")
    if browser_engine_btn.is_visible():
        browser_engine_btn.click()
        print("Explicitly selected Browser Web Speech fallback engine.")

    # 2. Click Start Voice Call
    start_voice_btn = page.locator("button:has-text('Start Voice Call')")
    start_voice_btn.click()
    print("Clicked Start Voice Call.")

    # Verify voice state transitions to Listening
    page.wait_for_selector("text=Listening...", timeout=10000)
    print("Audio engine transitioned to 'Listening...' state.")

    # 3. Simulate user speaking into microphone
    print("Simulating user speaking: 'What are the clinic hours and consultation fees?'")
    page.evaluate("window.__mockRecognitionInstance.simulateVoiceInput('What are the clinic hours and consultation fees?')")

    # 4. Verify user spoken message received and rendered in transcript
    page.wait_for_selector("text=What are the clinic hours and consultation fees?", timeout=15000)
    print("User spoken message received and rendered in transcript.")

    # Wait for assistant response to appear
    page.wait_for_selector("text=Here is the fee schedule at CareBridge Clinic", timeout=15000)
    print("Assistant response generated in transcript.")

    # 5. Verify SpeechSynthesis captured spoken response
    time.sleep(1)
    spoken_texts = page.evaluate("window.__spokenUtterances")
    print(f"Captured {len(spoken_texts)} spoken utterances via SpeechSynthesis:")
    for i, txt in enumerate(spoken_texts):
        print(f"  Utterance {i+1}: {txt[:80]}...")
    assert len(spoken_texts) > 0, "Expected at least one spoken utterance"
    assert "CareBridge Clinic" in spoken_texts[0], "Expected clinic info in spoken utterance"

    # 6. Test Mute Toggle
    mute_btn = page.locator("button[title='Mute Microphone']")
    mute_btn.click()
    page.wait_for_selector("text=Microphone Muted", timeout=5000)
    print("Muted audio engine successfully.")
    
    unmute_btn = page.locator("button[title='Unmute Microphone']")
    unmute_btn.click()
    page.wait_for_selector("text=Listening...", timeout=5000)
    print("Unmuted audio engine successfully.")

    # 7. Test End Voice Conversation
    end_btn = page.locator("button:has-text('End Voice Call')")
    end_btn.click()
    page.wait_for_selector("text=Ready / Standby", timeout=5000)
    print("Ended voice call. Audio engine returned to 'Ready / Standby' idle state.")


def test_missing_livekit_credentials_flow(page):
    print("\n--- Testing LiveKit Missing Credentials Error Flow ---")
    page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)

    # Click on LiveKit WebRTC engine
    livekit_btn = page.locator("button:has-text('LiveKit WebRTC')")
    livekit_btn.click()
    print("Selected LiveKit WebRTC engine.")

    # Attempt to start voice call without configured credentials
    page.locator("button:has-text('Start Voice Call')").click()
    print("Clicked Start Voice Call on unconfigured LiveKit engine.")

    # Verify actionable error is shown to the user
    page.wait_for_selector("text=LiveKit streaming credentials not configured", timeout=10000)
    print("Verified actionable error message rendered for unconfigured LiveKit streaming.")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 850},
            permissions=["microphone"]
        )
        page = context.new_page()

        try:
            test_text_booking_flow(page)
            test_browser_microphone_and_spoken_responses(page)
            test_missing_livekit_credentials_flow(page)
            print("\n=======================================================")
            print("ALL TEXT BOOKING, MOCKED VOICE, & LIVEKIT ERROR FLOWS PASSED!")
            print("=======================================================\n")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
