class VideoConferencingClient {
  constructor(roomId, userRole, applicantId = null, userName = null) {
    this.roomId = roomId;
    this.userRole = userRole; // 'admin' or 'applicant'
    this.applicantId = applicantId;
    this.userName = userName;
    this.peerConnection = null;
    this.localStream = null;
    this.remoteStream = null;
    this.ws = null;
    this.callActive = false;
    this.startTime = null;
    this.durationInterval = null;
    this.audioEnabled = true;
    this.videoEnabled = true;
    this.screenStream = null;
    this.cameraVideoTrack = null;
    this.mediaRecorder = null;
    this.recordedChunks = [];
    this.clientId = (window.crypto && window.crypto.randomUUID && window.crypto.randomUUID()) || `${Date.now()}-${Math.random()}`;
    this.pendingOffer = null;
  }

  async initConnection() {
    try {
      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      this.ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/video/${this.roomId}/`);
      this.ws.onopen = () => this.onWebSocketOpen();
      this.ws.onmessage = (e) => this.onWebSocketMessage(e);
      this.ws.onerror = (e) => this.onWebSocketError(e);
      this.ws.onclose = () => this.onWebSocketClose();
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      this.updateStatus('Connection failed. Please try again.', 'error');
    }
  }

  onWebSocketOpen() {
    console.log('WebSocket connected');
    this.updateStatus('Connected', 'success');
  }

  onWebSocketMessage(event) {
    const data = JSON.parse(event.data);
    console.log('WebSocket message:', data);
    if (data.sender && data.sender === this.clientId) return;

    switch (data.type) {
      case 'call-notification':
        if (this.userRole === 'applicant') {
          this.handleIncomingCall(data.data);
        }
        break;

      case 'call-accepted':
        if (this.userRole === 'admin') {
          this.handleCallAccepted();
        }
        break;

      case 'offer':
        this.handleOffer(data.data);
        break;

      case 'answer':
        this.handleAnswer(data.data);
        break;

      case 'ice-candidate':
        this.handleIceCandidate(data.data);
        break;

      case 'call-ended':
        this.endCall();
        break;
    }
  }

  onWebSocketError(error) {
    console.error('WebSocket error:', error);
    this.updateStatus('Connection error', 'error');
  }

  onWebSocketClose() {
    console.log('WebSocket disconnected');
  }

  async initiate() {
    this.callActive = true;
    this.startTime = Date.now();
    this.startCallTimer();

    try {
      this.localStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      this.cameraVideoTrack = this.localStream.getVideoTracks()[0] || null;

      this.attachLocalStream();
      this.syncMeetingUi();
      this.setupPeerConnection();

      this.sendWebSocketMessage({
        type: 'call-init',
        data: {
          caller: this.userName || this.userRole,
          timestamp: new Date().toISOString()
        }
      });

      this.updateStatus('Calling...', 'info');
    } catch (error) {
      console.error('Error accessing media:', error);
      this.updateStatus('Could not access camera/microphone', 'error');
    }
  }

  async accept() {
    this.callActive = true;
    this.startTime = Date.now();
    this.startCallTimer();

    try {
      this.localStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      this.cameraVideoTrack = this.localStream.getVideoTracks()[0] || null;

      this.attachLocalStream();
      this.syncMeetingUi();
      this.setupPeerConnection();

      this.sendWebSocketMessage({
        type: 'call-accept',
        data: {
          acceptor: this.userName || this.userRole,
          timestamp: new Date().toISOString()
        },
        applicant_id: this.applicantId
      });

      this.updateStatus('Call accepted. Connecting...', 'info');
    } catch (error) {
      console.error('Error accessing media:', error);
      this.updateStatus('Could not access camera/microphone', 'error');
    }
  }

  setupPeerConnection() {
    const config = {
      iceServers: [
        { urls: ['stun:stun.l.google.com:19302'] },
        { urls: ['stun:stun1.l.google.com:19302'] }
      ]
    };

    this.peerConnection = new RTCPeerConnection(config);

    if (this.localStream) {
      this.localStream.getTracks().forEach(track => {
        this.peerConnection.addTrack(track, this.localStream);
      });
    }

    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        this.sendWebSocketMessage({
          type: 'ice-candidate',
          data: event.candidate
        });
      }
    };

    this.peerConnection.ontrack = (event) => {
      console.log('Received remote track:', event.track);
      this.remoteStream = event.streams[0];
      const remoteVideo = document.getElementById('remoteVideo');
      const remoteAvatar = document.getElementById('remoteAvatar');
      if (remoteVideo) remoteVideo.srcObject = this.remoteStream;
      if (remoteAvatar) remoteAvatar.style.display = 'none';
      this.updateStatus('Connected', 'success');
    };

    this.peerConnection.onconnectionstatechange = () => {
      console.log('Connection state:', this.peerConnection.connectionState);
      if (this.peerConnection.connectionState === 'failed') {
        this.updateStatus('Connection failed', 'error');
      }
    };

    if (this.userRole === 'admin') {
      this.createOffer();
    } else if (this.pendingOffer) {
      const offer = this.pendingOffer;
      this.pendingOffer = null;
      this.handleOffer(offer);
    }
  }

  async createOffer() {
    try {
      const offer = await this.peerConnection.createOffer();
      await this.peerConnection.setLocalDescription(offer);
      this.sendWebSocketMessage({
        type: 'offer',
        data: offer
      });
    } catch (error) {
      console.error('Error creating offer:', error);
    }
  }

  async handleOffer(offer) {
    if (!this.peerConnection) {
      this.pendingOffer = offer;
      this.updateStatus('Incoming media ready', 'info');
      return;
    }

    try {
      await this.peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
      const answer = await this.peerConnection.createAnswer();
      await this.peerConnection.setLocalDescription(answer);
      this.sendWebSocketMessage({
        type: 'answer',
        data: answer
      });
    } catch (error) {
      console.error('Error handling offer:', error);
    }
  }

  async handleAnswer(answer) {
    try {
      await this.peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
    } catch (error) {
      console.error('Error handling answer:', error);
    }
  }

  async handleIceCandidate(candidate) {
    try {
      if (candidate) {
        await this.peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
      }
    } catch (error) {
      console.error('Error adding ICE candidate:', error);
    }
  }

  handleIncomingCall(data) {
    document.getElementById('incomingCallNotif').classList.remove('hidden');
    document.getElementById('incomingCallerName').textContent = (data.caller || 'Admin') + ' is calling...';
  }

  handleCallAccepted() {
    console.log('Call accepted by applicant');
    this.updateStatus('Call accepted', 'success');
    if (this.peerConnection) {
      this.createOffer();
    }
  }

  toggleAudio() {
    if (this.localStream) {
      const audioTracks = this.localStream.getAudioTracks();
      if (!audioTracks.length) return;
      const enabled = !audioTracks[0].enabled;
      audioTracks.forEach(track => track.enabled = enabled);
      this.audioEnabled = enabled;

      const btn = document.getElementById('toggleAudioBtn');
      this.setControlState(btn, enabled, 'Mic', 'Mute', enabled ? 'Mute' : 'Unmute');
    }
  }

  toggleVideo() {
    if (this.localStream) {
      const videoTracks = this.localStream.getVideoTracks();
      if (!videoTracks.length) return;
      const enabled = !videoTracks[0].enabled;
      videoTracks.forEach(track => track.enabled = enabled);
      this.videoEnabled = enabled;

      const btn = document.getElementById('toggleVideoBtn');
      this.setControlState(btn, enabled, 'Cam', 'Off', enabled ? 'Stop Video' : 'Start Video');
      const localAvatar = document.getElementById('localAvatar');
      if (localAvatar) localAvatar.style.display = enabled ? 'none' : 'grid';
    }
  }

  async toggleScreenShare() {
    if (this.screenStream) {
      this.stopScreenShare();
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      this.updateStatus('Screen sharing is not supported in this browser', 'error');
      return;
    }

    try {
      this.screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false
      });

      const screenTrack = this.screenStream.getVideoTracks()[0];
      const sender = this.peerConnection && this.peerConnection.getSenders()
        .find(item => item.track && item.track.kind === 'video');

      if (sender && screenTrack) {
        await sender.replaceTrack(screenTrack);
      }

      const localVideo = document.getElementById('localVideo');
      if (localVideo) localVideo.srcObject = this.screenStream;

      const shareBtn = document.getElementById('shareScreenBtn');
      if (shareBtn) {
        shareBtn.classList.add('active');
        const label = shareBtn.querySelector('span');
        if (label) label.textContent = 'Stop';
      }

      screenTrack.onended = () => this.stopScreenShare();
      this.updateStatus('Screen sharing', 'success');
    } catch (error) {
      console.error('Screen share error:', error);
      this.updateStatus('Screen share canceled', 'info');
    }
  }

  async stopScreenShare() {
    const screenTracks = this.screenStream ? this.screenStream.getTracks() : [];
    screenTracks.forEach(track => track.stop());
    this.screenStream = null;

    const sender = this.peerConnection && this.peerConnection.getSenders()
      .find(item => item.track && item.track.kind === 'video');

    if (sender && this.cameraVideoTrack) {
      await sender.replaceTrack(this.cameraVideoTrack);
    }

    this.attachLocalStream();

    const shareBtn = document.getElementById('shareScreenBtn');
    if (shareBtn) {
      shareBtn.classList.remove('active');
      const label = shareBtn.querySelector('span');
      if (label) label.textContent = 'Up';
    }

    this.updateStatus('Screen share stopped', 'info');
  }

  toggleRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.stop();
      return;
    }

    if (!this.localStream || typeof MediaRecorder === 'undefined') {
      this.updateStatus('Recording is not available', 'error');
      return;
    }

    const supportedType = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
      .find(type => MediaRecorder.isTypeSupported(type));

    try {
      this.recordedChunks = [];
      this.mediaRecorder = new MediaRecorder(this.localStream, supportedType ? { mimeType: supportedType } : undefined);

      this.mediaRecorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) this.recordedChunks.push(event.data);
      };

      this.mediaRecorder.onstop = () => this.downloadRecording();
      this.mediaRecorder.start(1000);

      const recordBtn = document.getElementById('recordBtn');
      if (recordBtn) {
        recordBtn.classList.add('active');
        const label = recordBtn.querySelector('span');
        if (label) label.textContent = 'Stop';
      }

      this.updateStatus('Recording started', 'success');
    } catch (error) {
      console.error('Recording error:', error);
      this.updateStatus('Could not start recording', 'error');
    }
  }

  downloadRecording() {
    const recordBtn = document.getElementById('recordBtn');
    if (recordBtn) {
      recordBtn.classList.remove('active');
      const label = recordBtn.querySelector('span');
      if (label) label.textContent = 'Rec';
    }

    if (!this.recordedChunks.length) return;

    const blob = new Blob(this.recordedChunks, { type: 'video/webm' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `video-room-${this.roomId}.webm`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    this.recordedChunks = [];
    this.updateStatus('Recording saved', 'success');
  }

  endCall() {
    this.callActive = false;
    if (this.durationInterval) clearInterval(this.durationInterval);

    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.stop();
    }

    if (this.screenStream) {
      this.screenStream.getTracks().forEach(track => track.stop());
      this.screenStream = null;
    }

    if (this.localStream) {
      this.localStream.getTracks().forEach(track => track.stop());
    }

    if (this.peerConnection) {
      this.peerConnection.close();
    }

    const videoModal = document.getElementById('videoModal');
    const incomingCallNotif = document.getElementById('incomingCallNotif');
    const callStatus = document.getElementById('callStatus');
    if (videoModal) videoModal.classList.add('hidden');
    if (incomingCallNotif) incomingCallNotif.classList.add('hidden');
    if (callStatus) callStatus.classList.add('hidden');

    this.sendWebSocketMessage({
      type: 'call-end',
      data: {}
    });
  }

  sendWebSocketMessage(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        ...data,
        sender: this.clientId
      }));
    }
  }

  updateStatus(message, type = 'info') {
    const statusDiv = document.getElementById('callStatus');
    const statusText = document.getElementById('callStatusText');
    if (!statusDiv || !statusText) return;
    statusText.textContent = message;
    statusDiv.classList.remove('hidden', 'bg-gray-800', 'bg-green-600', 'bg-red-600', 'bg-blue-600');

    if (type === 'success') {
      statusDiv.classList.add('bg-green-600');
    } else if (type === 'error') {
      statusDiv.classList.add('bg-red-600');
    } else {
      statusDiv.classList.add('bg-blue-600');
    }

    setTimeout(() => {
      if (type !== 'error') {
        statusDiv.classList.add('hidden');
      }
    }, 3000);
  }

  startCallTimer() {
    const timer = document.getElementById('callDuration');
    if (!timer) return;
    this.durationInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
      const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const seconds = String(elapsed % 60).padStart(2, '0');
      timer.textContent = `${minutes}:${seconds}`;
    }, 1000);
  }

  attachLocalStream() {
    const localVideo = document.getElementById('localVideo');
    const localAvatar = document.getElementById('localAvatar');
    if (localVideo) localVideo.srcObject = this.localStream;
    if (localAvatar) localAvatar.style.display = 'none';
  }

  setControlState(btn, enabled, onIcon, offIcon, label) {
    if (!btn) return;
    btn.classList.toggle('active', enabled);
    btn.classList.toggle('off', !enabled);
    btn.classList.toggle('bg-red-500', !enabled);
    btn.classList.toggle('hover:bg-red-600', !enabled);
    btn.classList.toggle('bg-blue-500', enabled);
    btn.classList.toggle('hover:bg-blue-600', enabled);

    const icon = btn.querySelector('.vc-control-icon') || btn.querySelector('span:first-child');
    const text = btn.querySelector('.vc-control-label') || btn.querySelector('span:last-child');
    if (icon) icon.textContent = enabled ? onIcon : offIcon;
    if (text) text.textContent = label;
  }

  syncMeetingUi() {
    const currentUserLabel = document.getElementById('currentUserLabel');
    const localNameTag = document.getElementById('localNameTag');
    const remoteNameTag = document.getElementById('remoteNameTag');
    const roomCodeLabel = document.getElementById('roomCodeLabel');
    const meetingTitle = document.getElementById('meetingTitle');

    const localName = this.userName || this.userRole || 'You';
    if (currentUserLabel) currentUserLabel.textContent = localName;
    if (localNameTag) localNameTag.textContent = localName;
    if (remoteNameTag) remoteNameTag.textContent = this.userRole === 'admin' ? 'Applicant' : 'Admin';
    if (roomCodeLabel) roomCodeLabel.textContent = String(this.roomId).slice(0, 12);
    if (meetingTitle && this.userRole) {
      meetingTitle.textContent = this.userRole === 'admin' ? 'Applicant Video Interview' : 'Interview Video Call';
    }
  }
}

// Initialize video conferencing buttons
document.addEventListener('DOMContentLoaded', function() {
  // These will be initialized by the specific pages (admin_calendar.html, applicant_portal.html)
  const videoModal = document.getElementById('videoModal');
  const toggleAudioBtn = document.getElementById('toggleAudioBtn');
  const toggleVideoBtn = document.getElementById('toggleVideoBtn');
  const endCallBtn = document.getElementById('endCallBtn');
  const shareScreenBtn = document.getElementById('shareScreenBtn');
  const recordBtn = document.getElementById('recordBtn');
  const acceptCallBtn = document.getElementById('acceptCallBtn');
  const rejectCallBtn = document.getElementById('rejectCallBtn');

  if (toggleAudioBtn) {
    toggleAudioBtn.addEventListener('click', function() {
      if (window.videoClient) window.videoClient.toggleAudio();
    });
  }

  if (toggleVideoBtn) {
    toggleVideoBtn.addEventListener('click', function() {
      if (window.videoClient) window.videoClient.toggleVideo();
    });
  }

  if (endCallBtn) {
    endCallBtn.addEventListener('click', function() {
      if (window.videoClient) window.videoClient.endCall();
    });
  }

  if (shareScreenBtn) {
    shareScreenBtn.addEventListener('click', function() {
      if (window.videoClient) window.videoClient.toggleScreenShare();
    });
  }

  if (recordBtn) {
    recordBtn.addEventListener('click', function() {
      if (window.videoClient) window.videoClient.toggleRecording();
    });
  }

  if (acceptCallBtn) {
    acceptCallBtn.addEventListener('click', function() {
      document.getElementById('incomingCallNotif').classList.add('hidden');
      if (window.videoClient) window.videoClient.accept();
      document.getElementById('videoModal').classList.remove('hidden');
    });
  }

  if (rejectCallBtn) {
    rejectCallBtn.addEventListener('click', function() {
      document.getElementById('incomingCallNotif').classList.add('hidden');
      if (window.videoClient) window.videoClient.endCall();
    });
  }

  const copyRoomBtn = document.getElementById('copyRoomBtn');
  if (copyRoomBtn) {
    copyRoomBtn.addEventListener('click', async function() {
      try {
        await navigator.clipboard.writeText(window.location.href);
        if (window.videoClient) window.videoClient.updateStatus('Room link copied', 'success');
      } catch (error) {
        if (window.videoClient) window.videoClient.updateStatus('Could not copy room link', 'error');
      }
    });
  }

  const fullscreenBtn = document.getElementById('fullscreenBtn');
  if (fullscreenBtn) {
    fullscreenBtn.addEventListener('click', function() {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen();
      else document.exitFullscreen();
    });
  }

  const sendChatBtn = document.getElementById('sendChatBtn');
  const chatInput = document.getElementById('chatInput');
  const chatMessages = document.getElementById('chatMessages');
  if (sendChatBtn && chatInput && chatMessages) {
    const sendLocalMessage = () => {
      const message = chatInput.value.trim();
      if (!message) return;
      const item = document.createElement('div');
      item.className = 'vc-msg';
      item.innerHTML = `<span class="vc-avatar vc-a5">Y</span><div class="vc-bubble"><small>You</small>${message.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</div><span class="vc-time">Now</span>`;
      chatMessages.appendChild(item);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      chatInput.value = '';
    };
    sendChatBtn.addEventListener('click', sendLocalMessage);
    chatInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') sendLocalMessage();
    });
  }
});
