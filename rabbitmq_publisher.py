"""
RabbitMQ message publisher for async notification handling
"""

import json
import os
from typing import Dict, Optional

import pika
from pika.exceptions import AMQPConnectionError


class NotificationPublisher:
    """RabbitMQ publisher for sending notification events"""

    def __init__(self):
        """Initialize RabbitMQ connection"""
        self.rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.getenv("RABBITMQ_USER", "swappo_user")
        self.rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "swappo_pass")
        self.queue_name = "notifications_queue"

        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None

        self._connect()

    def _connect(self):
        """Establish connection to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(
                self.rabbitmq_user, self.rabbitmq_password
            )

            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare queue (idempotent operation)
            self.channel.queue_declare(
                queue=self.queue_name, durable=True  # Persist messages to disk
            )

            print(
                f"✅ Connected to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port}"
            )

        except AMQPConnectionError as e:
            print(f"❌ Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def publish_notification(self, notification_data: Dict) -> bool:
        """
        Publish a notification event to RabbitMQ queue

        Args:
            notification_data: Notification payload dictionary

        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Reconnect if connection is closed
            if not self.connection or self.connection.is_closed:
                print("⚠️ RabbitMQ connection closed, reconnecting...")
                self._connect()

            if not self.channel:
                print("❌ No RabbitMQ channel available")
                return False

            # Convert to JSON
            message = json.dumps(notification_data)

            # Publish message
            self.channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type="application/json",
                ),
            )

            print(
                f"📤 Published notification to queue: {notification_data.get('type', 'unknown')}"
            )
            return True

        except Exception as e:
            print(f"❌ Failed to publish notification: {type(e).__name__}: {e}")
            return False

    def close(self):
        """Close RabbitMQ connection"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                print("✅ RabbitMQ connection closed")
        except Exception as e:
            print(f"⚠️ Error closing RabbitMQ connection: {e}")


# Global publisher instance
notification_publisher: Optional[NotificationPublisher] = None


def get_notification_publisher() -> NotificationPublisher:
    """Get or create global notification publisher instance"""
    global notification_publisher

    if notification_publisher is None:
        notification_publisher = NotificationPublisher()

    return notification_publisher
