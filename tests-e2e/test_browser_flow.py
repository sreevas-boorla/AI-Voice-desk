import pytest
import time
from playwright.sync_api import sync_playwright, expect

FRONTEND_URL = "http://localhost:5180"

def test_receptionist_verified_reschedule_and_admin_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # 1. Navigate to VoiceDesk Receptionist page
        page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)
        expect(page).to_have_title("VoiceDesk — CareBridge Clinic AI Receptionist")

        # 2. Switch to Text Mode for deterministic test entry
        text_mode_btn = page.locator("button:has-text('Text Chat Mode')")
        text_mode_btn.click()

        # 3. Step 1: Verified lookup of CB-1001
        chat_input = page.locator("form input[type='text']")
        chat_input.fill("Please verify booking CB-1001 with code 4821")
        page.locator("button[type='submit']:has-text('Send')").click()

        # Wait for assistant response
        page.wait_for_selector("text=Access verified for booking", timeout=15000)
        expect(page.locator("text=Access verified for booking").first).to_be_visible()

        # 4. Step 2: Request Reschedule
        chat_input.fill("Reschedule CB-1001 to tomorrow afternoon")
        page.locator("button[type='submit']:has-text('Send')").click()

        # Wait for Confirmation Card to render
        page.wait_for_selector("text=RESCHEDULE Request", timeout=15000)
        expect(page.locator("button:has-text('Confirm & Persist')").first).to_be_visible()

        # 5. Step 3: Explicit Confirmation click
        page.locator("button:has-text('Confirm & Persist')").first.click()

        # Wait for confirmation success message
        page.wait_for_selector("text=successfully rescheduled", timeout=15000)
        expect(page.locator("text=successfully rescheduled").first).to_be_visible()

        # 6. Step 4: Switch to Admin Portal
        page.locator("button:has-text('Admin Portal')").click()

        # Check if login is needed
        if page.locator("input[type='password']").is_visible():
            page.locator("form input[type='text']").fill("admin")
            page.locator("input[type='password']").fill("CareBridge2026!")
            page.locator("button:has-text('Sign In to Dashboard')").click()

        # 7. Step 5: Verify Updated Admin Record in appointments table
        page.wait_for_selector("text=Clinic Administration Dashboard", timeout=15000)
        
        # Check CB-1001 row
        cb1001_row = page.locator("tr:has-text('CB-1001')")
        expect(cb1001_row).to_be_visible()
        expect(cb1001_row.locator("text=RESCHEDULED")).to_be_visible()

        browser.close()

def test_mobile_responsive_layout():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Mobile viewport: 390x844 (standard mobile device)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)

        expect(page.locator("text=VoiceDesk").first).to_be_visible()
        expect(page.locator("button:has-text('Receptionist')").first).to_be_visible()
        
        # Test navigation on mobile
        page.locator("button:has-text('Admin Portal')").first.click()
        expect(page.locator("text=CareBridge Staff Portal").first).to_be_visible()
        
        browser.close()

if __name__ == "__main__":
    test_receptionist_verified_reschedule_and_admin_flow()
    test_mobile_responsive_layout()
    print("All Playwright E2E and Mobile Layout Tests Passed Successfully!")
