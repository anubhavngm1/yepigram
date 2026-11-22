import os
import sys
import base64
import json
import time
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import database

def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')

def b64_decode(data: str) -> bytes:
    return base64.b64decode(data.encode('utf-8'))

class UserClient:
    def __init__(self, user_id, display_name):
        self.user_id = user_id
        self.display_name = display_name
        # 1. Identity Key (Long-term Curve25519)
        self.identity_private = x25519.X25519PrivateKey.generate()
        self.identity_public = self.identity_private.public_key()
        
        # 2. Signed Pre-Key (Medium-term)
        self.signed_prekey_private = x25519.X25519PrivateKey.generate()
        self.signed_prekey_public = self.signed_prekey_private.public_key()
        
        # 3. One-Time Pre-Keys
        self.one_time_private_keys = [x25519.X25519PrivateKey.generate() for _ in range(5)]
        self.one_time_public_keys = [k.public_key() for k in self.one_time_private_keys]

        # Active Session Keys (peer_id -> symmetric key)
        self.sessions = {}

    def get_registration_bundle(self):
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "identity_key": b64_encode(self.identity_public.public_bytes_raw()),
            "signed_prekey": b64_encode(self.signed_prekey_public.public_bytes_raw()),
            "signed_prekey_sig": "sig_valid",
            "one_time_prekeys": [b64_encode(k.public_bytes_raw()) for k in self.one_time_public_keys]
        }

    def initiate_x3dh_with_peer(self, peer_bundle):
        peer_id = peer_bundle["user_id"]
        peer_ik = x25519.X25519PublicKey.from_public_bytes(b64_decode(peer_bundle["identity_key"]))
        peer_spk = x25519.X25519PublicKey.from_public_bytes(b64_decode(peer_bundle["signed_prekey"]))
        peer_opk = None
        if peer_bundle.get("one_time_prekey"):
            peer_opk = x25519.X25519PublicKey.from_public_bytes(b64_decode(peer_bundle["one_time_prekey"]))

        # Ephemeral Key for this session
        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()

        # Triple/Quadruple Diffie-Hellman (X3DH)
        # DH1 = Identity_A x SignedPreKey_B
        dh1 = self.identity_private.exchange(peer_spk)
        # DH2 = Ephemeral_A x Identity_B
        dh2 = ephemeral_private.exchange(peer_ik)
        # DH3 = Ephemeral_A x SignedPreKey_B
        dh3 = ephemeral_private.exchange(peer_spk)
        
        dh_material = dh1 + dh2 + dh3
        if peer_opk:
            dh4 = ephemeral_private.exchange(peer_opk)
            dh_material += dh4

        # Derive 256-bit Master Key via HKDF
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"Yepigram-E2EE-Salt-v1",
            info=b"DoubleRatchetMasterKey"
        ).derive(dh_material)

        self.sessions[peer_id] = derived_key
        return b64_encode(ephemeral_public.public_bytes_raw())

    def accept_x3dh_from_peer(self, peer_id, peer_ik_bytes, peer_ephemeral_bytes):
        peer_ik = x25519.X25519PublicKey.from_public_bytes(peer_ik_bytes)
        peer_ek = x25519.X25519PublicKey.from_public_bytes(peer_ephemeral_bytes)

        # Mirror DH calculations on Bob's side
        dh1 = self.signed_prekey_private.exchange(peer_ik)
        dh2 = self.identity_private.exchange(peer_ek)
        dh3 = self.signed_prekey_private.exchange(peer_ek)
        
        # Use first OPK
        dh_material = dh1 + dh2 + dh3
        if self.one_time_private_keys:
            dh4 = self.one_time_private_keys[0].exchange(peer_ek)
            dh_material += dh4

        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"Yepigram-E2EE-Salt-v1",
            info=b"DoubleRatchetMasterKey"
        ).derive(dh_material)

        self.sessions[peer_id] = derived_key

    def encrypt_message(self, peer_id, plaintext_str):
        key = self.sessions[peer_id]
        aesgcm = AESGCM(key)
        iv = os.urandom(12)
        ciphertext = aesgcm.encrypt(iv, plaintext_str.encode('utf-8'), None)
        return {
            "iv": b64_encode(iv),
            "ciphertext": b64_encode(ciphertext)
        }

    def decrypt_message(self, peer_id, payload):
        key = self.sessions[peer_id]
        aesgcm = AESGCM(key)
        iv = b64_decode(payload["iv"])
        ciphertext = b64_decode(payload["ciphertext"])
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext, None)
        return decrypted_bytes.decode('utf-8')

def run_tests():
    print("=" * 65)
    print("🚀 YEPIGRAM E2EE SIGNAL PROTOCOL INTEGRATION VERIFICATION")
    print("=" * 65)

    # 1. Initialize SQLite Database
    database.init_db()
    print("✔ Step 1: Local SQLite database initialized.")

    # 2. Create User Alice and User Bob
    alice = UserClient("alice_101", "Alice Jenkins")
    bob = UserClient("bob_202", "Bob Smith")

    # 3. Register Pre-Key Bundles
    database.register_user(alice.user_id, alice.display_name, "alice@yepigram.org", 
                           b64_encode(alice.identity_public.public_bytes_raw()))
    alice_bundle = alice.get_registration_bundle()
    database.save_prekeys(alice_bundle["user_id"], alice_bundle["identity_key"], 
                          alice_bundle["signed_prekey"], alice_bundle["signed_prekey_sig"], 
                          alice_bundle["one_time_prekeys"])

    database.register_user(bob.user_id, bob.display_name, "bob@yepigram.org", 
                           b64_encode(bob.identity_public.public_bytes_raw()))
    bob_bundle = bob.get_registration_bundle()
    database.save_prekeys(bob_bundle["user_id"], bob_bundle["identity_key"], 
                          bob_bundle["signed_prekey"], bob_bundle["signed_prekey_sig"], 
                          bob_bundle["one_time_prekeys"])

    print("✔ Step 2: Both Alice and Bob generated & registered Curve25519 Pre-Key bundles.")

    # 4. Alice fetches Bob's Pre-Key bundle from Server
    fetched_bob_bundle = database.get_prekey_bundle("bob_202")
    assert fetched_bob_bundle is not None
    assert fetched_bob_bundle["one_time_prekey"] is not None
    print("✔ Step 3: Server delivered Bob's one-time Pre-Key bundle to Alice.")

    # 5. Alice initiates X3DH and derives shared master key
    alice_ephemeral_b64 = alice.initiate_x3dh_with_peer(fetched_bob_bundle)
    print("✔ Step 4: Alice completed X3DH key exchange and derived AES-256 session key.")

    # 6. Bob receives Alice's initial handshake and mirrors key derivation
    bob.accept_x3dh_from_peer("alice_101", 
                              alice.identity_public.public_bytes_raw(), 
                              b64_decode(alice_ephemeral_b64))
    print("✔ Step 5: Bob accepted handshake and derived identical symmetric key.")

    assert alice.sessions["bob_202"] == bob.sessions["alice_101"]
    print("✔ Step 6: Cryptographic keys match perfectly between Alice and Bob!")

    # 7. Alice encrypts real message
    secret_text = "Hey Bob! This message is 100% End-to-End Encrypted via Yepigram Signal Ratchet."
    encrypted_payload = alice.encrypt_message("bob_202", secret_text)
    print(f"✔ Step 7: Alice encrypted message -> Ciphertext ({len(encrypted_payload['ciphertext'])} bytes).")

    # 8. Test Offline Queue: Bob is offline, message stored in database
    database.queue_offline_message("msg_001", "bob_202", "alice_101", json.dumps(encrypted_payload))
    print("✔ Step 8: Server successfully queued encrypted message for offline recipient.")

    # 9. Bob comes online, server flushes queue
    queued_messages = database.fetch_queued_messages("bob_202")
    assert len(queued_messages) == 1
    received_payload = json.loads(queued_messages[0]["encrypted_payload"])

    # 10. Bob decrypts payload
    decrypted_text = bob.decrypt_message("alice_101", received_payload)
    assert decrypted_text == secret_text
    print(f"✔ Step 9: Bob decrypted message successfully: \"{decrypted_text}\"")

    # 11. Verify zero-knowledge cleanup on server
    empty_queue = database.fetch_queued_messages("bob_202")
    assert len(empty_queue) == 0
    print("✔ Step 10: Verified server automatically purged message from queue (zero-knowledge privacy).")

    print("=" * 65)
    print("🎉 ALL 10 E2EE CRYPTOGRAPHIC & QUEUEING TESTS PASSED!")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
