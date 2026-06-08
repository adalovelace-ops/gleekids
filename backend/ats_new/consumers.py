import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import Schedule
from django.contrib.auth.models import User

class VideoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'video_{self.room_id}'
        self.user_role = None
        self.applicant_id = None

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        message_type = content.get('type')
        sender = content.get('sender')

        if message_type == 'call-init':
            self.user_role = 'admin'
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'call_notification',
                    'sender': sender,
                    'data': content.get('data', {})
                }
            )

        elif message_type == 'call-accept':
            self.user_role = 'applicant'
            self.applicant_id = content.get('applicant_id')
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'call_accepted',
                    'sender': sender,
                    'data': content.get('data', {})
                }
            )

        elif message_type == 'offer':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'webrtc_offer',
                    'sender': sender,
                    'data': content.get('data')
                }
            )

        elif message_type == 'answer':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'webrtc_answer',
                    'sender': sender,
                    'data': content.get('data')
                }
            )

        elif message_type == 'ice-candidate':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'ice_candidate',
                    'sender': sender,
                    'data': content.get('data')
                }
            )

        elif message_type == 'call-end':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'call_ended',
                    'sender': sender,
                    'data': {}
                }
            )

    async def call_notification(self, event):
        await self.send_json({
            'type': 'call-notification',
            'sender': event.get('sender'),
            'data': event['data']
        })

    async def call_accepted(self, event):
        await self.send_json({
            'type': 'call-accepted',
            'sender': event.get('sender'),
            'data': event['data']
        })

    async def webrtc_offer(self, event):
        await self.send_json({
            'type': 'offer',
            'sender': event.get('sender'),
            'data': event['data']
        })

    async def webrtc_answer(self, event):
        await self.send_json({
            'type': 'answer',
            'sender': event.get('sender'),
            'data': event['data']
        })

    async def ice_candidate(self, event):
        await self.send_json({
            'type': 'ice-candidate',
            'sender': event.get('sender'),
            'data': event['data']
        })

    async def call_ended(self, event):
        await self.send_json({
            'type': 'call-ended',
            'sender': event.get('sender'),
            'data': event['data']
        })
