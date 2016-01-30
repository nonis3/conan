'''
	@ Harris Christiansen (Harris@HarrisChristiansen.com)
	2016-01-24
	For: Purdue Hackers - Battleship
	Battleship Server - Written in Python
'''

import socket
import time
from thread import start_new_thread
import threading
import json
import urllib2
########## Start Web Sockets ##########
from autobahn.twisted.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory
import sys
from twisted.python import log
from twisted.internet import reactor
## End WS ##

############################################ Socket Connection ############################################

API_URL = "http://localhost:8888/api/"
port = 23345

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', port))
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Make Address Reusable - No Lockout
s.listen(20)

games = []
players = []

DEFAULT_DELAY_LENGTH = 1.001

############################################ Battleship Game Logic ############################################

class BattleshipGame(threading.Thread):
	def __init__(self,p1,p2):
		super(self.__class__, self).__init__()
		self.p1Obj = p1
		self.p2Obj = p2
		self.p1 = p1[1]
		self.p2 = p2[1]
		self.p1Ships = [[0 for x in range(8)] for x in range(8)]
		self.p2Ships = [[0 for x in range(8)] for x in range(8)]
		self.p1Ready = 0
		self.p2Ready = 0
		self.playersConnected = True
		self.gamePlaying = True
		self.listeners = []
		self.delayLength = DEFAULT_DELAY_LENGTH

	def sendMsg(self,msg):
		try:
			self.p1.sendall(msg+"\n")
		except:
			self.setClosed(self.p1)
		try:
			self.p2.sendall(msg+"\n")
		except:
			self.setClosed(self.p2)

	def sendMsgP(self,p,msg):
		try:
			p.sendall(msg+"\n")
		except:
			self.setClosed(p)

	def setReady(self,p):
		if(p is self.p1):
			self.p1Ready = 1
		else:
			self.p2Ready = 1

	def setClosed(self,p):
		if(self.p1 != None):
			self.p1Ready = -1
			self.p1.close()
			players.remove(self.p1Obj)
			self.p1 = None
	
		if(self.p2 != None):
			self.p2Ready = -1
			self.p2.close()
			players.remove(self.p2Obj)
			self.p2 = None

		self.gamePlaying = False
		self.playersConnected = False

	def getCord(self,p):
		try:
			data = p.recv(2)
		except: # Timeout
			print("Error: Timeout Receiving Coord, Ending Game")
			self.setClosed(p)
			return False

		if (not data) or (not isinstance(data,(str))): # Client Closed Connection
			self.setClosed(p)
			return False
		try:
			c = ord(data[0])-65
			r = int(data[1])

			if(c<0 or c>=8 or r<0 or r>=8):
				self.sendMsgP(p,"Error: Invalid Input - Out Of Bounds")
				self.setClosed(p)
				return False

			return (c,r)
		except (ValueError, IndexError) as e:
			self.sendMsgP(p,"Error: Invalid Input - Parse Integer")
			self.setClosed(p)
			return False

	def placeShip(self,p,c1,c2,ship):
		if(c1[0]==c2[0]):
			for i in range(min(c1[1],c2[1]),max(c1[1]+1,c2[1]+1)):
				if(p is self.p1):
					self.p1Ships[c1[0]][i] = ship
				else:
					self.p2Ships[c1[0]][i] = ship
		else:
			for i in range(min(c1[0],c2[0]),max(c1[0]+1,c2[0]+1)):
				if(p is self.p1):
					self.p1Ships[i][c1[1]] = ship
				else:
					self.p2Ships[i][c1[1]] = ship

	def placeShips(self,p):
		ships = [("Destroyer",2),("Submarine",3),("Cruiser",3),("Battleship",4),("Carrier",5)]

		for ship in ships:
			self.sendMsgP(p,ship[0]+"("+str(ship[1])+"):")
			if(self.p1Ready==-1 or self.p2Ready==-1):
				return False

			c1 = self.getCord(p)
			if(self.p1Ready==-1 or self.p2Ready==-1):
				return False

			c2 = self.getCord(p)
			if(self.p1Ready==-1 or self.p2Ready==-1):
				return False

			if(c1 != False and c2 != False and (c1[0]==c2[0] or c1[1]==c2[1]) and (abs(c1[0]-c2[0])+abs(c1[1]-c2[1])+1)==ship[1]):
				self.placeShip(p,c1,c2,ships.index(ship)+1)
			else:
				print("Received Invalid Input - Ship Cords: "+str(c1)+", "+str(c2))
				self.sendMsgP(p,"Error: Invalid Input - Ship Cords")
				self.setClosed(p)
				return False

		self.setReady(p)
		return True

	def placeMove(self,p):
		self.sendMsgP(p,"Enter Coordinates")
		c1 = self.getCord(p)
		if(c1 == False):
			return False
		if(p is self.p1):
			hit = self.p2Ships[c1[0]][c1[1]]
			hitResult = ""
			if(hit > 0):
				self.p2Ships[c1[0]][c1[1]] = 0 - hit
				if any(hit in sublist for sublist in self.p2Ships):
					self.sendMsgP(p,"Hit")
					hitResult = "Hit"
				else:
					self.sendMsgP(p,"Sunk")
					hitResult = "Sunk"
				self.checkGame()
			else:
				self.sendMsgP(p,"Miss")
				hitResult = "Miss"

			for listener in self.listeners: # Notify GameViewer
				listener.sendMsg("M|"+self.p1Obj[0]+"|"+str(c1[0])+"|"+str(c1[1])+"|"+hitResult)
			
		else:
			hit = self.p1Ships[c1[0]][c1[1]]
			hitResult = ""
			if(hit > 0):
				self.p1Ships[c1[0]][c1[1]] = 0 - hit
				if any(hit in sublist for sublist in self.p1Ships):
					self.sendMsgP(p,"Hit")
					hitResult = "Hit"
				else:
					self.sendMsgP(p,"Sunk")
					hitResult = "Sunk"
				self.checkGame()
			else:
				self.sendMsgP(p,"Miss")
				hitResult = "Miss"
				
			for listener in self.listeners: # Notify GameViewer
				listener.sendMsg("M|"+self.p2Obj[0]+"|"+str(c1[0])+"|"+str(c1[1])+"|"+hitResult)

		self.setReady(p)
		return True

	def checkGame(self):
		if(self.gamePlaying):
			if(max(max(l) for l in self.p1Ships) <= 0):
				# Player 2 Won
				self.gamePlaying = False
				content = urllib2.urlopen(API_URL+'game/'+self.p2Obj[0]+"/"+self.p1Obj[0]).read()
			if(max(max(l) for l in self.p2Ships) <= 0):
				# Player 1 Won
				self.gamePlaying = False
				content = urllib2.urlopen(API_URL+'game/'+self.p1Obj[0]+"/"+self.p2Obj[0]).read()

	def run(self):
		global games, players
		games.append(self)

		while self.playersConnected:
			self.p1Ready=self.p2Ready=0
			self.sendMsgP(self.p1,"Welcome To Battleship! You Are Playing:"+self.p2Obj[0].split("-")[0])
			self.sendMsgP(self.p2,"Welcome To Battleship! You Are Playing:"+self.p1Obj[0].split("-")[0])
			self.gamePlaying = True
			self.p1Ships = [[0 for x in range(8)] for x in range(8)]
			self.p2Ships = [[0 for x in range(8)] for x in range(8)]
			start_new_thread(self.placeShips, (self.p1,))
			start_new_thread(self.placeShips, (self.p2,))

			while(self.p1Ready==0 or self.p2Ready==0):
				time.sleep(0.003)
				continue

			if(self.p1Ready==-1 or self.p2Ready==-1):
				break

			for listener in self.listeners: # Tell GameViewers to rejoin to get correct map
				listener.sendMsg("rejoin")

			while self.gamePlaying:
				time.sleep(self.delayLength) # Adjustable Move Delay Length
				self.p1Ready=self.p2Ready=0
				start_new_thread(self.placeMove, (self.p1,))
				start_new_thread(self.placeMove, (self.p2,))

				while(self.p1Ready==0 or self.p2Ready==0):
					time.sleep(0.003)
					continue

				if(self.p1Ready==-1 or self.p2Ready==-1):
					break

		print "Game Ended"
		for listener in self.listeners: # Tell GameViewers that game is closed
			listener.sendMsg("closed")
		games.remove(self)

############################################ Web GUI Client ############################################

class GameViewer(WebSocketServerProtocol):

	def onConnect(self, request):
		self.currentGame = -1

	def onOpen(self):
		self.currentGame = -1

	def sendMsg(self, msg):
		self.sendMessage(msg, False)

	def onMessage(self, payload, isBinary):
		global games

		data = format(payload.decode('utf8'))

		if "games" in data:
			gameIDs = []
			for game in games:
				gameIDs.append(game._Thread__ident)

			self.sendMsg("G|"+json.dumps(gameIDs));

		elif "join" in data:
			# Remove Current Listener
			for game in games:
				if(game._Thread__ident == self.currentGame) and (self in game.listeners):
					game.listeners.remove(self)
					break

			self.currentGame = int(data.split()[1])
			for game in games:
				if(game._Thread__ident == self.currentGame):
					game.listeners.append(self)
					self.sendMsg("B|"+json.dumps([game.p1Obj[0],game.p1Ships,game.p2Obj[0],game.p2Ships]))
					break

		elif "delay" in data:
			for game in games:
				if(game._Thread__ident == self.currentGame):
					game.delayLength = float(data.split()[1])
					break

	def onClose(self, wasClean, code, reason):
		global games
		for game in games:
			if(game._Thread__ident == self.currentGame) and (self in game.listeners): # Maybe Modify to check every game for self in listeners list
				game.listeners.remove(self)
				break
				

############################################ Main Thread ############################################

player1 = player2 = None

def getPlayer1():
	global player1, players
	while player1==None:
		p, addr = s.accept()
		p.settimeout(100) # TODO: Set to 10
		try:
			userID = p.recv(1024)
			if not userID: # Client Closed Connection
				p.close()
				continue
			userID = userID.strip("\r\n ")+"-"+str(addr[1])
		except:
			p.close()
			continue

		if not "API_KEY_HERE" in userID:
			# Verify userID (API_KEY)
			content = urllib2.urlopen(API_URL+'auth/'+userID).read()
			if "False" in content: # Invalid API_KEY
				p.sendall("False\n")
				continue
			userID = content.strip("\r\n ")

		print "Client Connected: " + addr[0] + ":" + str(addr[1]) + " - " + str(userID)
		p.sendall("True\n") # Let Know Connection Successful

		player1 = (userID,p)
		players.append(player1)
		break

def getPlayer2():
	global player2, players
	while player2==None:
		p, addr = s.accept()
		p.settimeout(100) # TODO: Set to 10
		try:
			userID = p.recv(1024)
			if not userID: # Client Closed Connection
				p.close()
				continue
			userID = userID.strip("\r\n ")+"-"+str(addr[1])
		except:
			p.close()
			continue

		if not "API_KEY_HERE" in userID:
			# Verify userID (API_KEY)
			content = urllib2.urlopen(API_URL+'auth/'+userID).read()
			if "False" in content: # Invalid API_KEY
				p.sendall("False\n")
				continue
			userID = content.strip("\r\n ")

		print "Client Connected: " + addr[0] + ":" + str(addr[1]) + " - " + str(userID)
		p.sendall("True\n") # Let Know Connection Successful

		player2 = (userID,p)
		players.append(player2)
		break

def startGameThread():
	global player1, player2
	while True:
		player1 = player2 = None

		start_new_thread(getPlayer1,())
		start_new_thread(getPlayer2,())

		while(player1==None or player2==None):
			time.sleep(0.1)
			continue

		thread = BattleshipGame(player1,player2)
		thread.setDaemon(True) # Set as background thread
		thread.start()

	s.close()


start_new_thread(startGameThread,())


########## Start Web Sockets ##########
# log.startLogging(sys.stdout)
factory = WebSocketServerFactory(u"ws://127.0.0.1:23346", debug=False)
factory.protocol = GameViewer
# factory.setProtocolOptions(maxConnections=2)
reactor.listenTCP(23346, factory)
reactor.run()
## End WS ##