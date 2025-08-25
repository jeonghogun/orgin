# pyright: reportGeneralTypeIssues=false
"""
Firebase Firestore service for data operations
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.config.settings import settings
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger("origin")


class FirebaseService:
    """Firebase Firestore service for data operations"""

    def __init__(self):
        if not settings.FIREBASE_SERVICE_ACCOUNT_PATH:
            raise Exception("Firebase service account path not configured")

        try:
            # Initialize Firebase Admin SDK
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise

    # Room operations
    async def create_room(self, room_data: Dict[str, Any]) -> str:
        """Create a new room in Firestore"""
        try:
            room_ref = self.db.collection("rooms").document()
            room_data["room_id"] = room_ref.id
            room_data["created_at"] = datetime.utcnow().isoformat() + "Z"
            room_ref.set(room_data)
            logger.info(f"Room created in Firebase: {room_ref.id}")
            return room_ref.id
        except Exception as e:
            logger.error(f"Failed to create room in Firebase: {e}")
            raise

    async def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get room data from Firestore"""
        try:
            room_ref = self.db.collection("rooms").document(room_id)
            room_doc = room_ref.get()
            if room_doc.exists:
                return room_doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get room from Firebase: {e}")
            raise

    async def get_rooms_by_owner(self, owner_id: str) -> List[Dict[str, Any]]:
        """Get all rooms for an owner from Firestore."""
        try:
            rooms_ref = self.db.collection("rooms")
            query = rooms_ref.where("owner_id", "==", owner_id)
            docs = query.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get rooms by owner from Firebase: {e}")
            raise

    async def delete_room(self, room_id: str) -> bool:
        """Recursively delete a room and its subcollections in Firestore."""
        try:
            room_ref = self.db.collection("rooms").document(room_id)
            self._delete_collection(room_ref.collection("messages"), 100)
            # Add other subcollections here if they exist (e.g., reviews)
            room_ref.delete()
            logger.info(f"Deleted room {room_id} from Firebase.")
            return True
        except Exception as e:
            logger.error(f"Failed to delete room {room_id} from Firebase: {e}")
            return False

    def _delete_collection(self, coll_ref, batch_size):
        """Helper to delete a collection in batches."""
        docs = coll_ref.limit(batch_size).stream()
        deleted = 0
        for doc in docs:
            doc.reference.delete()
            deleted += 1

        if deleted >= batch_size:
            self._delete_collection(coll_ref, batch_size)

    # Message operations
    async def save_message(self, room_id: str, message_data: Dict[str, Any]) -> str:
        """Save a message to Firestore"""
        try:
            message_ref = (
                self.db.collection("rooms")
                .document(room_id)
                .collection("messages")
                .document()
            )
            message_data["message_id"] = message_ref.id
            message_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            message_ref.set(message_data)
            logger.info(f"Message saved in Firebase: {message_ref.id}")
            return message_ref.id
        except Exception as e:
            logger.error(f"Failed to save message in Firebase: {e}")
            raise

    async def get_room_messages(
        self, room_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get messages for a room from Firestore"""
        try:
            messages_ref = (
                self.db.collection("rooms").document(room_id).collection("messages")
            )
            messages = (
                messages_ref.order_by("timestamp", direction=firestore.Query.ASCENDING)
                .limit(limit)
                .stream()
            )
            return [msg.to_dict() for msg in messages]
        except Exception as e:
            logger.error(f"Failed to get messages from Firebase: {e}")
            raise

    # Review operations
    async def create_review(self, review_data: Dict[str, Any]) -> str:
        """Create a new review in Firestore"""
        try:
            review_ref = self.db.collection("reviews").document()
            review_data["review_id"] = review_ref.id
            review_data["created_at"] = datetime.utcnow().isoformat() + "Z"
            review_ref.set(review_data)
            logger.info(f"Review created in Firebase: {review_ref.id}")
            return review_ref.id
        except Exception as e:
            logger.error(f"Failed to create review in Firebase: {e}")
            raise

    async def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get review data from Firestore"""
        try:
            review_ref = self.db.collection("reviews").document(review_id)
            review_doc = review_ref.get()
            if review_doc.exists:
                return review_doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get review from Firebase: {e}")
            raise

    async def update_review(self, review_id: str, update_data: Dict[str, Any]) -> bool:
        """Update review data in Firestore"""
        try:
            review_ref = self.db.collection("reviews").document(review_id)
            review_ref.update(update_data)
            logger.info(f"Review updated in Firebase: {review_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update review in Firebase: {e}")
            raise

    async def save_panel_report(
        self,
        review_id: str,
        round_number: int,
        panel_name: str,
        report_data: Dict[str, Any],
    ) -> str:
        """Save panel report to Firestore"""
        try:
            report_ref = (
                self.db.collection("reviews")
                .document(review_id)
                .collection("reports")
                .document()
            )
            report_data["report_id"] = report_ref.id
            report_data["round_number"] = round_number
            report_data["panel_name"] = panel_name
            report_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            report_ref.set(report_data)
            logger.info(f"Panel report saved in Firebase: {report_ref.id}")
            return report_ref.id
        except Exception as e:
            logger.error(f"Failed to save panel report in Firebase: {e}")
            raise

    async def save_consolidated_report(
        self, review_id: str, round_number: int, report_data: Dict[str, Any]
    ) -> str:
        """Save consolidated report to Firestore"""
        try:
            report_ref = (
                self.db.collection("reviews")
                .document(review_id)
                .collection("consolidated_reports")
                .document()
            )
            report_data["report_id"] = report_ref.id
            report_data["round_number"] = round_number
            report_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            report_ref.set(report_data)
            logger.info(f"Consolidated report saved in Firebase: {report_ref.id}")
            return report_ref.id
        except Exception as e:
            logger.error(f"Failed to save consolidated report in Firebase: {e}")
            raise

    async def get_consolidated_report(
        self, review_id: str, round_number: int
    ) -> Optional[Dict[str, Any]]:
        """Get consolidated report from Firestore"""
        try:
            reports_ref = (
                self.db.collection("reviews")
                .document(review_id)
                .collection("consolidated_reports")
            )
            reports = (
                reports_ref.where("round_number", "==", round_number).limit(1).stream()
            )
            for report in reports:
                return report.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get consolidated report from Firebase: {e}")
            raise

    async def get_room_reviews(self, room_id: str) -> List[Dict[str, Any]]:
        """Get all reviews for a room from Firestore"""
        try:
            reviews_ref = self.db.collection("reviews")
            reviews = reviews_ref.where("room_id", "==", room_id).stream()
            # Sort in memory to avoid index requirement
            review_list = [review.to_dict() for review in reviews]
            review_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return review_list
        except Exception as e:
            logger.error(f"Failed to get room reviews from Firebase: {e}")
            raise

    async def save_final_report(
        self, review_id: str, report_data: Dict[str, Any]
    ) -> str:
        """Save final report to Firestore"""
        try:
            report_ref = (
                self.db.collection("reviews")
                .document(review_id)
                .collection("final_reports")
                .document()
            )
            report_data["report_id"] = report_ref.id
            report_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
            report_ref.set(report_data)
            logger.info(f"Final report saved in Firebase: {report_ref.id}")
            return report_ref.id
        except Exception as e:
            logger.error(f"Failed to save final report in Firebase: {e}")
            raise

    async def get_final_report(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get final report from Firestore"""
        try:
            reports_ref = (
                self.db.collection("reviews")
                .document(review_id)
                .collection("final_reports")
            )
            reports = reports_ref.limit(1).stream()
            for report in reports:
                return report.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get final report from Firebase: {e}")
            raise
