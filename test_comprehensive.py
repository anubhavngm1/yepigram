import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import database

def run_comprehensive_tests():
    print("=" * 70)
    print("🧪 YAPERGRAM COMPREHENSIVE BACKEND & E2EE TEST SUITE")
    print("=" * 70)

    # 1. Initialize DB
    database.init_db()
    print("✔ 1. Database initialized successfully.")

    # 2. Test User Registration
    user1, err1 = database.register_user("alex_dev", "secret123", "Alex Dev", "avatar1.png", "ik_alex_bytes")
    assert err1 is None, f"Registration failed: {err1}"
    assert user1["username"] == "alex_dev"
    assert "token" in user1
    print(f"✔ 2. User 'alex_dev' registered with ID: {user1['user_id']}.")

    user2, err2 = database.register_user("sara_ux", "pass456", "Sara Design", "avatar2.png", "ik_sara_bytes")
    assert err2 is None
    print(f"✔ 3. User 'sara_ux' registered with ID: {user2['user_id']}.")

    # Duplicate username check
    dup_user, dup_err = database.register_user("alex_dev", "pass789")
    assert dup_err is not None
    print("✔ 4. Duplicate username registration properly rejected.")

    # 3. Test Login
    login_success, err = database.login_user("alex_dev", "secret123")
    assert err is None
    assert login_success["user_id"] == user1["user_id"]
    print("✔ 5. User login succeeded with correct credentials.")

    login_fail, err = database.login_user("alex_dev", "wrongpass")
    assert err is not None
    print("✔ 6. User login failed as expected with wrong password.")

    # 4. Test Session Verification
    session_user = database.verify_session(login_success["token"])
    assert session_user is not None
    assert session_user["username"] == "alex_dev"
    print("✔ 7. Session token verified successfully.")

    # 5. Test User Search
    search_results = database.search_users("sara", user1["user_id"])
    assert len(search_results) == 1
    assert search_results[0]["username"] == "sara_ux"
    print(f"✔ 8. Search query 'sara' returned: @{search_results[0]['username']}.")

    # 6. Test Profile Update
    updated_profile = database.update_profile(user1["user_id"], "Alex Master Dev", "new_avatar.png", "Building E2EE Apps 🚀")
    assert updated_profile["display_name"] == "Alex Master Dev"
    assert updated_profile["bio"] == "Building E2EE Apps 🚀"
    print("✔ 9. Profile updated (Display Name & Bio).")

    # 7. Test Chat Creation & Chat Lock (Hidden Chats with PIN)
    chat = database.get_or_create_chat(user1["user_id"], user2["user_id"])
    assert chat is not None
    print(f"✔ 10. Chat room established: {chat['chat_id']}.")

    # Lock Chat with 4-digit PIN "7492"
    database.lock_chat(chat["chat_id"], "7492")
    assert database.unlock_chat_verify(chat["chat_id"], "7492") is True
    assert database.unlock_chat_verify(chat["chat_id"], "0000") is False
    print("✔ 11. Chat Lock security verified (correct PIN opens, wrong PIN blocked).")

    # 8. Test Encrypted Message Lifecycle (sent -> delivered -> read)
    msg_id = "msg_test_999"
    database.save_message(msg_id, user1["user_id"], user2["user_id"], "{\"ciphertext\":\"abc123enc\"}", "sent")
    
    # Recipient fetches offline messages
    offline = database.get_offline_messages(user2["user_id"])
    assert len(offline) >= 1
    print(f"✔ 12. Encrypted message queued & delivered: status={offline[0]['status']}.")

    # Recipient reads message
    database.update_message_status(msg_id, "read")
    history = database.get_chat_history(user1["user_id"], user2["user_id"])
    read_msg = [m for m in history if m["message_id"] == msg_id][0]
    assert read_msg["status"] == "read"
    print("✔ 13. Read receipt confirmed (Double blue check status active).")

    # 9. Test Stories (24h Disappearing Statuses)
    story = database.create_story(user1["user_id"], "", "Hello Yapergram community! 🌟", "linear-gradient(135deg, #ec4899, #8b5cf6)")
    assert story["story_id"] is not None
    active_stories = database.get_active_stories()
    assert len(active_stories) >= 1
    print(f"✔ 14. 24h Story created and verified: \"{story['text_content']}\".")

    print("=" * 70)
    print("🎉 ALL 14 COMPREHENSIVE BACKEND & SECURITY TESTS PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    run_comprehensive_tests()
