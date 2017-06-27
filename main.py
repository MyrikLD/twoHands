import fcntl
import json
import random
import re
import socket
import struct
import urllib
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
from cv2 import imshow, namedWindow, setWindowProperty
from platform import machine
from threading import Thread
from time import sleep

import cv2
import numpy as np

from btns import desk, Button
from log import Log


def get_ip_address(ifname):
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		addr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15]))[20:24])
	except:
		addr = None
	return addr


STAGE = 0
LANCAM = list()
WindowName = 'Term'
FULLSCREEN = True
RUN = True
__version__ = 0.6
log = None
ip = get_ip_address('eth0' if machine() == 'armv7l' else 'wlp3s0')
log = Log(ip)
cam = list()

server = None

with open('settings.json') as json_data:
	settings = json.load(json_data)


def geturl(url):
	log.debug("SEND: " + str(url))
	try:
		url = urllib.urlopen(url)
	except Exception as e:
		log.error(e)
		return e
	ret = url.getcode()
	if ret != 200:
		log.warning('RET: ' + str(ret))
	url.close()
	return ret


class CamHandler(BaseHTTPRequestHandler):
	streams = None

	def log_message(self, format, *args):
		if len(args) > 0:
			if args[0] == 'GET /0 HTTP/1.1':
				return
			else:
				log.debug(args[0])

	def do_GET(self):
		path = self.path.split('/')[1:]
		data = path[-1]
		name = data
		args = dict()
		end = str()
		server = self.client_address[0]

		if '?' in data:
			name, args = data.split('?')
			args = args.split('&')
			ar = dict()
			for i in range(len(args)):
				r = args[i].split('=')
				if len(r) == 2:
					ar.update({r[0]: r[1]})
				else:
					ar.update({r[0]: str()})
			args = ar

		if '.' in name:
			name, end = name.split('.')

		if name == 'execute_1':
			game.setServer(server)
			param_1 = int(args.get('param_1', ''))
			game.start(param_1)
			self.send_response(200)
			self.send_header('Content-type', 'application/json')
			self.end_headers()
			self.wfile.write('{success: 1}')

		if name == '0' and end == '':
			game.setServer(server)
			self.send_response(200)
			self.send_header('Content-type', 'application/json')
			self.end_headers()
			self.wfile.write('{state_int_1: %i, state_int_2: %i}' % (game.stage, game.round))

		if end == 'mjpg':
			try:
				self.send_response(200)
				self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--jpgboundary')
				self.send_header('Connection', 'keep-alive')
				self.end_headers()
			except Exception:
				return
			while RUN and self.connection._sock != None:
				try:
					num = int(name)
					img = str(self.streams[num])
					if len(img) == 0:
						continue
					try:
						data = b'--jpgboundary\r\n'
						data += b'Content-type: image/jpeg\r\n'
						data += b'Content-length: %i\r\n' % len(img)
						data += b'\r\n'
						data += img
						data += b'\r\n'
						self.connection._sock.send(data)
					except Exception as e:
						break
				except KeyboardInterrupt:
					break
			return

		if end == 'html' and len(path) == 1 and name.isdigit():
			self.send_response(200)
			self.send_header('Content-type', 'text/html')
			self.end_headers()
			self.wfile.write('<html><head></head><body>')
			self.wfile.write('<img src="/%s.mjpg"/>' % int(name))
			self.wfile.write('</body></html>')


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
	"""Handle requests in a separate thread."""


class VideoStream:
	frame = None
	grabbed = None
	stream = None
	stopped = True
	paused = False
	src = None

	net = None

	def __init__(self, src=0):
		if type(src) == int:
			self.src = src
			log.info('Creating camera %s' % src)
			self.stream = cv2.VideoCapture(src)
			self.stream.set(3, 320)
			self.stream.set(4, 240)
			try:
				# self.grabbed, self.frame = self.stream.read()
				self.grabbed = self.stream.grab()
			except Exception as e:
				log.error('Camera %s error: %s' % (self.src, e))
			self.stopped = False
		else:
			pattern = r"^http:\/\/(?P<ip>[0-9.]+):(?P<port>[0-9]+)\/(?P<fn>.+)\.(?P<ft>.+)$"
			self.net = re.search(pattern, src).groupdict()
			self.src = str(src)
			self.stopped = False
			self.paused = True
		self.th = Thread(target=self.update, args=()).start()

	def netconn(self):
		stream = None
		while stream is None:
			try:
				stream = urllib.urlopen(self.src)
			except Exception as e:
				log.error(self.src + ': ' + str(e))
				sleep(1)
		return stream

	def update(self):
		if type(self.src) == str:
			stream = None
			data = bytes()
			while RUN:
				if self.stopped:
					return
				if self.paused:
					continue

				if stream is None:
					stream = self.netconn()

				try:
					data += stream.read(1)
				except Exception as e:
					log.error(e)
					data = bytes()
					stream.close()
					stream = self.netconn()
					continue

				b = data.find(b'\r\n\r\n')

				if b == -1:
					continue

				a = data.find(b'--')

				if a != -1 and b != -1:
					head = data[a:b].split('\r\n')
					for i in head:
						if 'length' in i:
							l = int(i[i.find(': ') + 2:])

					jpg = bytes()
					data = bytes()
					while len(jpg) < l:
						try:
							jpg += stream.read(l - len(jpg))
						except Exception as e:
							stream.close()
							stream = self.netconn()

					self.frame = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

		else:
			while RUN:
				if self.stopped:
					return
				if self.paused:
					continue
				try:
					self.grabbed = self.stream.grab()
					_, self.frame = self.stream.retrieve()
				except Exception as e:
					log.error('Camera %s error: %s' % (self.src, e))

	def read(self):
		img = self.frame
		return img

	def pause(self):
		self.paused = True
		return self

	def start(self):
		self.paused = False
		return self

	def stop(self):
		self.stopped = True
		return self

	def __del__(self):
		self.stop()
		self.stream.release()

	def __str__(self):
		f = self.frame
		if f is not None:
			return cv2.imencode(".png", self.frame)[1].tostring()
		return ''


def getImg(c):
	for i in c:
		d = i.read()
		yield d


def comp(*img):
	img = list(img)

	while any(i is None for i in img):
		img.remove(None)

	if len(img) == 0:
		vis = np.zeros((1, 1), np.uint8)
		frame = cv2.resize(vis, tuple(settings['size']))
		return frame

	h = [i.shape[0] for i in img]
	w = [i.shape[1] for i in img]

	sz = (max(h), sum(w), 3)

	vis = np.zeros(sz, np.uint8)
	for i in range(len(img)):
		vis[:h[i], sum(w[:i]):sum(w[:(i + 1)])] = img[i]

	frame = cv2.resize(vis, tuple(settings['size']))
	return frame


class Game:
	stage = 0
	round = 0
	btns = list()
	server = '127.0.0.1'

	def __init__(self):
		self.stage = 0
		self.round = 0
		Button.callback = self.clicked

	def setServer(self, s):
		if self.server != s:
			self.server = s
			log.info('New server: ' + str(s))

	def start(self, num):
		if self.stage == num:
			log.debug('Double start round '+str(num))
			return None

		if num != 0:
			log.info('Starting round ' + str(num))
			self.getRandBtns()
		else:
			log.info('Stop game')
			desk.leds(False)
			self.btns = list()

		self.round = 0
		self.stage = num

	def getRandBtns(self):
		desk.leds(False)
		for i in desk.L:
			i.clicked = False
		for i in desk.R:
			i.clicked = False

		self.btns = list([random.choice(desk.L), random.choice(desk.R)])
		for i in self.btns:
			i.led(True)
		log.info('Random buttons: ' + str([str(i) for i in self.btns]))

	def endStage(self):
		log.info('End stage: ' + str(self.stage))
		geturl('http://%s:3000/events/0/event_1?param_1=%i' % (self.server, self.stage))
		if self.stage != 3:
			self.round = 0
			self.stage = 0

	def nextRound(self):
		endRound = {1: 3, 2: 2, 3: 1}
		log.info('End round: %i/%i' % (self.round+1, endRound[self.stage]+1))
		if self.round == endRound[self.stage]:
			self.endStage()
			return
		else:
			self.round += 1
			self.getRandBtns()

	def resetRound(self):
		log.info('Reset round')
		self.round = 0
		self.getRandBtns()

	def clicked(self, btn):
		if self.stage == 0:
			return

		log.info('Click: ' + str(btn))

		if btn not in self.btns:
			self.resetRound()
		else:
			btn.led(False)
			if self.btns[0].clicked and self.btns[1].clicked:
				self.nextRound()


def createFrame():
	frames = list()

	if game.stage == 1:
		frames = getImg(cam)
	elif game.stage == 2:
		a = cam[::-1]
		frames = getImg(a)
	elif game.stage == 3:
		for i in LANCAM:
			if i.paused:
				i.start()
		frames = getImg(LANCAM)

	frame = comp(*frames)
	return frame


def window(*cam):
	global STAGE
	global RUN

	while RUN:
		frame = createFrame()

		if frame is not None:
			imshow(WindowName, frame)

		key = cv2.waitKey(1)

		if key & 0xFF == 27:
			RUN = False
			break

		if key & 0xFF == 32:
			STAGE = (STAGE + 1) % 3

	for i in cam:
		i.stop()
	cv2.destroyAllWindows()
	exit(-1)


def serve():
	global server
	CamHandler.streams = cam
	server = ThreadedHTTPServer(('', settings['port']), CamHandler)
	log.info("Server started")
	server.serve_forever()


game = Game()

if __name__ == '__main__':
	WindowName = str(ip)
	other = settings.get(ip, [])
	log.info('Version: %s' % __version__)
	log.info('OpenCV: %s' % cv2.__version__)
	log.info('My addr: %s' % ip)
	log.info('Other: %s' % other)
	cam = list([VideoStream(0).start(), VideoStream(1).start()])

	if FULLSCREEN:
		namedWindow(WindowName, cv2.WND_PROP_FULLSCREEN)
		if cv2.__version__.startswith('2.'):
			setWindowProperty(WindowName, cv2.WND_PROP_FULLSCREEN, cv2.cv.CV_WINDOW_FULLSCREEN)
		if cv2.__version__.startswith('3.'):
			setWindowProperty(WindowName, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

	th = Thread(target=window, args=(cam))
	th.start()
	th1 = Thread(target=serve, args=())
	th1.start()

	LANCAM = list()
	for i in other:
		url = 'http://' + str(i[0]) + ':' + str(settings['port']) + '/' + str(i[1]) + '.mjpg'
		d = VideoStream(url)
		log.info('NetCam created: ' + url)
		LANCAM.append(d)

	while RUN:
		pass
	log.info('Exit')
	server.shutdown()
	th1.join(1)
	th.join(1)
