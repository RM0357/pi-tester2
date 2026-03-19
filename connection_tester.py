#!/usr/bin/python3 -u

import os
import re
import time
import serial
import signal
import subprocess

try:
	from termcolor import colored
except ImportError:
	def colored(text, color=None, on_color=None, attrs=None):
		return text


# Todo: state machine aufblasen
# Todo: print funktionen nur temporär, als service dann wieder normal printen


def print_todo(message):
	print(colored(message, 'yellow'))

def print_ok(message):
	print(colored(message, 'green'))

def print_error(message):
	print(colored(message, 'red', attrs=["bold", "blink"]))

def print_syscall(message):
	print(colored(message, 'cyan'))

def print_debug(message):
	print(colored(message, 'magenta'))

def print_status(value):
	message= f"Status:  {value}"
	if value == 0:
		print_ok(message)
	else:
		print_error(message)

def print_decode(message):
	print(message)

def print_decode_ok(message):
	print(colored(message, 'green'))

def print_decode_nok(message):
	print(colored(message, 'red'))

# nRF also prints in color....
def print_modem_tx(message):
	print("========================  TX  ========================\n  ", end="")
	print(message.strip().replace('\n','\n  '))
	print("======================================================")

def print_modem_rx(message):
	print("------------------------  RX  ------------------------\n  ", end="")
	print(message.strip().replace('\r\n\r\n','\r\n').replace('\n','\n  '))
	print("------------------------------------------------------")





class GPIOs(object):
	
	def __init__(self):
		'''Perform electrical configuration of GPIOs and init attributes'''
		
		self.Outputs= {
			'RST': 524,
			'EN': -1
		}
		
		for Pin, Number in self.Outputs.items():
			if Number == -1:
				print_debug(f"Currently not wired: '{Pin}'")
				continue
			else:
				if not os.path.islink(f"/sys/class/gpio/gpio{Number}"):
					print_syscall( f"echo {Number} > /sys/class/gpio/export" ) # Todo: will be removed
					subprocess.run( f"echo {Number} > /sys/class/gpio/export", shell= True )
					
					print_syscall( f"echo out > /sys/class/gpio/gpio{Number}/direction" ) # Todo: will be removed
					subprocess.run( f"echo out > /sys/class/gpio/gpio{Number}/direction", shell= True )
	
	
	def Set(self, Name, State):
		'''Set the state of an output'''
		
		if Name in self.Outputs:
			if self.Outputs[Name] == -1:
				print_debug(f"Currently not wired: '{Name}'")
				return
			if State in [0,1]:
				print_syscall( f"echo {State} > /sys/class/gpio/gpio{self.Outputs[Name]}/value" ) # Todo: will be removed
				subprocess.run( f"echo {State} > /sys/class/gpio/gpio{self.Outputs[Name]}/value", shell= True )
			else:
				print(f"Unknown state: '{State}' ('{self.Outputs[Name]}')")
		else:
			print(f"Unknown output: '{Name}'")
	
	
	def Toggle(self, Name, State, Pause= 0.01):
		'''Toggle the state of an output'''
		
		self.Set( Name, State )
		time.sleep( Pause )
		self.Set( Name, (1-State) )



class SerialModem(object):
	
	def __init__(self):
		'''Open the serial port and init attributes'''
		
		self.State = "Init"     # Todo: TargetState != ActState ?
		
		self.Target = 'SLM'
		
		self.Modem = serial.Serial('/dev/ttyUSB0', baudrate= 115200, timeout= 1);    # SW emulated: 4800
		
		self.StatusPattern= re.compile( r"#XPPP: (?P<Running>0|1),(?P<Connected>0|1)", re.MULTILINE )  # Todo: auch gegen DiagPatterns tauschen
		
		self.DiagPatterns= {
			'XPPP': re.compile( r"#XPPP: (?P<Running>0|1),(?P<Connected>0|1)", re.MULTILINE ),
			'XSIM': re.compile( r"%XSIM: (?P<state>[0-9]+)(,(?P<cause>[^,]+))?", re.MULTILINE ),
			'CFUN': re.compile( r"\+CFUN: (?P<fun>[0-9]+)", re.MULTILINE ),
			'XCBAND': re.compile( r"%XCBAND: (?P<band>[0-9]+)", re.MULTILINE ),
			'CESQ': re.compile( r"\+CESQ: (?P<rxlev>[0-9]+),(?P<ber>[0-9]+),(?P<rscp>[0-9]+),(?P<ecno>[0-9]+),(?P<rsrq>[0-9]+),(?P<rsrp>[0-9]+)", re.MULTILINE ),
			'XMONITOR': re.compile( r"%XMONITOR: (?P<reg_status>[0-9]+)(,(?P<full_name>[^,]+),(?P<short_name>[^,]+),(?P<plmn>[^,]+))?", re.MULTILINE ),
			'XSYSTEMMODE': re.compile( r"%XSYSTEMMODE: (?P<LTE_M_support>[0-9]+),(?P<NB_IoT_support>[0-9]+),(?P<GNSS_support>[0-9]+),(?P<LTE_preference>[0-9]+)", re.MULTILINE ),
			'CGDCONT': re.compile( r"\+CGDCONT: (?P<cid>[0-9]+),(?P<PDP_type>[^,]+),(?P<APN>[^,]+),(?P<PDP_addr>[^,]+),(?P<d_comp>[^,]+),(?P<h_comp>[^,]+)?", re.MULTILINE )
		}
		
		# todo: echo ist noch gesetzt, vorher clearen ?
		
		# nach AT+CFUN=1 kommt die PPP response (irgendwann) automatisch
	
	
	def ClearBuffer(self):
		'''Read and print the input buffer (e.g. to clear startup messages)'''
		
		self.Modem.timeout = 1
		
		try:
			raw_data = self.Modem.read(1000)
			Response = raw_data.decode("utf-8", errors="replace").strip()    # Todo: länge definieren, kures + langes timeout? clear funktion mit kurzem timeout
		except:
			Response= "---  No response (error)  ---"
		
		print_modem_rx(f"{Response}")
		
		return Response
	
	
	def Send(self, Command):
		'''Send a message to the modem and return the response'''
		
		Response= ""
		self.Modem.timeout = 0.2
		
		if not Command.endswith('\n'):
			Command += '\n'
		
		print_modem_tx(f"{Command}")
		self.Modem.write(Command.encode('utf-8'))
		
		try:
			raw_data = self.Modem.read(1000)
			Response = raw_data.decode("utf-8", errors="replace").strip()    # Todo: länge definieren, kures + langes timeout? clear funktion mit kurzem timeout
		except:
			print(colored("UART read error", 'red'))
		
		print_modem_rx(f"{Response}")
		
		return Response
	
	
	def AtSend(self, Command):
		'''Send an AT command to the modem including format check'''
		
		if not Command.startswith("at ") and self.Target == 'MOSH':
			Command = f"at {Command}"
		
		if not Command.endswith("\r\n"):
			Command = f"{Command}\r\n"
		
		return self.Send(Command)
	
	
	def Config(self):
		'''Send AT commands to the modem to configure APN and bandlock'''
		
		self.AtSend('AT%XBANDLOCK=2,"10000000000010000000"')    # 8 and 20
#		self.AtSend('AT+CGDCONT=0,"IPV4V6","m2m.public.at"')    # internet.t-mobile.at, business.gprsinternet
#		self.AtSend('AT+COPS=1,2,"23203",7')                    # Manual network selection, Magenta, E-UTRAN
	
	
	def On(self):
		'''Send an AT command to the modem to set "functional mode 1" (full functionality)'''
		
		self.AtSend("AT+CFUN=1")                  # Todo: PPP_wait()  ?   (funktioniert wahrscheinlich auch nur wenn man aus off kommt)
	#	self.State= "On"
	
	
	def Off(self):
		'''Send an AT command to the modem to set "functional mode 0" (minimum functionality)'''
		
		self.AtSend("AT+CFUN=0")
	#	self.State= "Off"              # Todo: also influended by GPIOs, not only commands...
		
		# Todo: +CFUN=0 causes writing to NVM. When using +CFUN=0, take NVM war into account
		#       eventuell durch +CFUN=4 (flight mode) ersetzen ?
	
	
	def PPP_on(self):
		'''Send an AT command to the modem to start PPP'''
		
		self.AtSend("AT#XPPP=1")
	
	
	def PPP_off(self):
		'''Send an AT command to the modem to stop PPP'''
		
		self.AtSend("AT#XPPP=0")
	
	
	def PPP_check(self):
		'''Send an AT command to the modem to get the current PPP status'''
		
		Response = self.AtSend("AT#XPPP?")
		Result = self.StatusPattern.match(Response)
		
		if Result:
			print_todo( f"Running: {Result.group('Running')}, Connected: {Result.group('Connected')}" )
			return Result.group('Running'), Result.group('Connected')     # Todo: 'unknown' state einführen?
		else:
			return '0','0'
	
	
	def FlightMode(self):
		'''Send an AT command to the modem to set "functional mode 4" (flight mode)'''
		
		self.AtSend("AT+CFUN=4")
	
	
	def CheckMode(self):
		'''Check if mode is set to 'normal', e.g. reinit after press of reset button'''
		
		Response = self.AtSend("AT+CFUN?")
		Result= self.DiagPatterns['CFUN'].match(Response)
		if Result:
			if Result.group('fun') ==  '0':
				print_decode_nok("CFUN.fun= 0 -> 'Minimum functionality mode' -> set on")
				self.On()
		else:
			print_error(f"Format error 'AT+CFUN?':\n{Response}")
	
	
	def CheckUART(self):
		'''Check if UART is still responding'''
		
		Response = self.AtSend("AT+CGSN")
		if Response == "":
			return False
		else:
			return True
	
	
	def Diag(self):
		'''Send several AT command to the modem to get diagnostic information'''
		
		self.AtSend("AT+CFUN?")
		self.AtSend("AT+CESQ")
		self.AtSend("AT%XMONITOR")
		self.AtSend("AT%XCBAND")
		self.AtSend("AT%XSYSTEMMODE?")
	
	
	def DiagDecode(self, LogFile):
		'''Send some dianostic commands to the modem and decode the response'''
		
		Time = time.strftime("%H:%M:%S", time.gmtime())    # "%d.%m.%Y %H:%M:%S"
		Fun  = ""
		Band = ""
		Rsrq = ""
		Rsrp = ""
		Reg_status = ""
		
		
#		Response = self.AtSend("AT%XSIM?")
#		Result= self.DiagPatterns['XSIM'].match(Response)
#		if Result:
#			if Result.group('state') ==  '0': print_decode_nok("XSIM.state= 0 -> 'UICC not initialized'")
#			if Result.group('state') ==  '1': print_decode_ok ("XSIM.state= 1 -> 'UICC initialization OK'")
#			
#			if Result.group('cause') is not None:
#				if Result.group('cause') ==  '1': print_decode_nok("XSIM.cause= 1 -> 'PIN required'")
#				if Result.group('cause') ==  '2': print_decode_nok("XSIM.cause= 2 -> 'PIN2 required'")
#				if Result.group('cause') ==  '3': print_decode_nok("XSIM.cause= 3 -> 'PUK required (PIN blocked)'")
#				if Result.group('cause') ==  '4': print_decode_nok("XSIM.cause= 4 -> 'PUK2 required (PIN2 blocked)'")
#				if Result.group('cause') ==  '5': print_decode_nok("XSIM.cause= 5 -> 'PUK blocked'")
#				if Result.group('cause') ==  '6': print_decode_nok("XSIM.cause= 6 -> 'PUK2 blocked'")
#				if Result.group('cause') ==  '7': print_decode_nok("XSIM.cause= 7 -> 'Device personalization blocked'")
#				if Result.group('cause') ==  '8': print_decode_nok("XSIM.cause= 8 -> 'IMEI lock blocked'")
#				if Result.group('cause') ==  '9': print_decode_nok("XSIM.cause= 9 -> 'USIM card failure'")
#				if Result.group('cause') == '10': print_decode_nok("XSIM.cause= 10 -> 'USIM card changed'")
#				if Result.group('cause') == '11': print_decode_nok("XSIM.cause= 11 -> 'USIM profile changed'")
#				if Result.group('cause') == '12': print_decode_nok("XSIM.cause= 12 -> 'GNSS mode only (UICC not initialized)'")
		
		Response = self.AtSend("AT+CFUN?")
		Result= self.DiagPatterns['CFUN'].match(Response)
		if Result:
			Fun = Result.group('fun')
			if Result.group('fun') ==  '0': print_decode_nok("CFUN.fun= 0 -> 'Minimum functionality mode'")
			if Result.group('fun') ==  '1': print_decode_ok ("CFUN.fun= 1 -> 'Normal mode'")
			if Result.group('fun') ==  '2': print_decode_nok("CFUN.fun= 2 -> 'Receive only mode'")
			if Result.group('fun') ==  '4': print_decode_nok("CFUN.fun= 4 -> 'Flight mode'")
			if Result.group('fun') == '21': print_decode_nok("CFUN.fun= 21 -> 'LTE is activated'")
			if Result.group('fun') == '31': print_decode_nok("CFUN.fun= 31 -> 'GNSS is activated'")
			if Result.group('fun') == '41': print_decode_nok("CFUN.fun= 41 -> 'UICC is activated'")
		else:
			print_error(f"Format error 'AT+CFUN?':\n{Response}")
		
		Response = self.AtSend("AT%XCBAND")
		Result= self.DiagPatterns['XCBAND'].match(Response)
		if Result:
			Band = Result.group('band')
			if Result.group('band') == '0':
				print_decode_nok("XCBAND.band= 0 -> 'Current information not available'")
			else:
				print_decode_ok(f"XCBAND.band= {Result.group('band')}")
		else:
			print_error(f"Format error 'AT%XCBAND':\n{Response}")
		
		Response = self.AtSend("AT+CESQ")
		Result= self.DiagPatterns['CESQ'].match(Response)
		if Result:
			Rsrq = Result.group('rsrq')
			if Result.group('rsrq') == '255':
				print_decode_nok("CESQ.rsrq= 255 -> 'Not known or not detectable'")
			else:
				print_decode_ok(f"CESQ.rsrq= {Result.group('rsrq')}")
			
			Rsrp = Result.group('rsrp')
			if Result.group('rsrp') == '255':
				print_decode_nok("CESQ.rsrp= 255 -> 'Not known or not detectable'")
			else:
				print_decode_ok(f"CESQ.rsrp= {Result.group('rsrp')}")
		else:
			print_error(f"Format error 'AT+CESQ':\n{Response}")
		
		Response = self.AtSend("AT%XMONITOR")
		Result= self.DiagPatterns['XMONITOR'].match(Response)
		if Result:
			Reg_status = Result.group('reg_status')
			if Result.group('reg_status') ==  '0': print_decode_nok("XMONITOR.reg_status= 0 -> 'Not registered, not currently searching'")
			if Result.group('reg_status') ==  '1': print_decode_ok ("XMONITOR.reg_status= 1 -> 'Registered, home network'")
			if Result.group('reg_status') ==  '2': print_decode_nok("XMONITOR.reg_status= 2 -> 'Not registered, currently searching'")
			if Result.group('reg_status') ==  '3': print_decode_nok("XMONITOR.reg_status= 3 -> 'Registration denied'")
			if Result.group('reg_status') ==  '4': print_decode_nok("XMONITOR.reg_status= 4 -> 'Unknown'")
			if Result.group('reg_status') ==  '5': print_decode_ok ("XMONITOR.reg_status= 5 -> 'Registered, roaming'")
			if Result.group('reg_status') == '90': print_decode_nok("XMONITOR.reg_status= 90 -> 'Not registered due to failure'")
			
			if Result.group('full_name') is not None:
				print_decode_ok(f"XMONITOR.full_name= {Result.group('full_name')}")
			
			if Result.group('short_name') is not None:
				print_decode_ok(f"XMONITOR.short_name= {Result.group('short_name')}")
			
			if Result.group('plmn') is not None:
				print_decode_ok(f"XMONITOR.plmn= {Result.group('plmn')}")
		else:
			print_error(f"Format error 'AT%XMONITOR':\n{Response}")
		
#		Response = self.AtSend("AT%XSYSTEMMODE?")
#		Result= self.DiagPatterns['XSYSTEMMODE'].match(Response)
#		if Result:
#			if Result.group('LTE_M_support') == '0': print_decode_nok("XSYSTEMMODE.LTE_M_support= 0 -> 'LTE-M not supported'")
#			if Result.group('LTE_M_support') == '1': print_decode_ok ("XSYSTEMMODE.LTE_M_support= 1 -> 'LTE-M supported'")
#			
#			if Result.group('NB_IoT_support') == '0': print_decode_nok("XSYSTEMMODE.NB_IoT_support= 0 -> 'NB-IoT not supported'")
#			if Result.group('NB_IoT_support') == '1': print_decode_ok ("XSYSTEMMODE.NB_IoT_support= 1 -> 'NB-IoT supported'")
#			
#			if Result.group('GNSS_support') == '0': print_decode("XSYSTEMMODE.GNSS_support= 0 -> 'GNSS not supported'")
#			if Result.group('GNSS_support') == '1': print_decode("XSYSTEMMODE.GNSS_support= 1 -> 'GNSSsupported'")
#			
#			if Result.group('LTE_preference') == '0': print_decode_nok("XSYSTEMMODE.LTE_preference= 0 -> 'No preference'")
#			if Result.group('LTE_preference') == '1': print_decode_ok ("XSYSTEMMODE.LTE_preference= 1 -> 'LTE-M preferred'")
#			if Result.group('LTE_preference') == '2': print_decode_nok("XSYSTEMMODE.LTE_preference= 2 -> 'NB-IoT preferred'")
#			if Result.group('LTE_preference') == '3': print_decode_nok("XSYSTEMMODE.LTE_preference= 3 -> 'Priority from network (LTE-M)'")
#			if Result.group('LTE_preference') == '4': print_decode_nok("XSYSTEMMODE.LTE_preference= 4 -> 'Priority from network (NB-IoT)'")
#		else:
#			print_error(f"Format error 'AT%XSYSTEMMODE?':\n{Response}")
#		
#		# Todo:
#		Response = self.AtSend("AT+CGSN")  # einmalig reicht
#		Response = self.AtSend("AT+CGDCONT?")  # -> decodieren
		
		LogFile.write(f"{Time},{Fun},{Band},{Rsrq},{Rsrp},{Reg_status}\n")
	
	
	def Close(self):
		'''Close the serial port'''
		
		self.Modem.close()



class ConnectionManager(object):
	
	def __init__(self, folder=None, location="", card="", cable="", antenna=""):
		'''Configure and open the serial port, init GPIOs, init attributes'''
		
		self.Shutdown= False
		self.LastStart= time.time()
		
		# Todo: passt nicht ganz hierher, hier ist aber die Execute schon vorhanden... (Execute ganz auslagern?)
		self.Execute( ["stty","-F","/dev/ttyUSB0","115200"] )
		self.Execute( ["stty","-F","/dev/ttyUSB0","-echo","-onlcr"] )
		
		print("Init serial console")
		self.Modem = SerialModem()
		
		print("Init GPIOs")
		self.Pins = GPIOs()
		
		if folder is None:
			print("Start logfile\n")
			while folder == "" or folder is None:
				print("Folder name: ", end="")
				folder= input().strip()
				if os.path.isdir(f"./{folder}"):
					folder= ""
		
		self.LogFolder = f"./{folder}"
		if not os.path.exists(self.LogFolder):
			os.mkdir(self.LogFolder)
		
		if not location:
			print("Location: ", end="")
			location= input().strip()
		if not card:
			print("M2 card:  ", end="")
			card= input().strip()
		if not cable:
			print("Cabel:    ", end="")
			cable= input().strip()
		if not antenna:
			print("Antenna:  ", end="")
			antenna= input().strip()
		
		NotesFile = open( f"./{self.LogFolder}/notes.txt", 'w' )
		NotesFile.write(f"Location: {location}\n")
		NotesFile.write(f"M2 card:  {card}\n")
		NotesFile.write(f"Cabel:    {cable}\n")
		NotesFile.write(f"Antenna:  {antenna}\n")
		NotesFile.close()
		
		self.LogFile= open( f"./{self.LogFolder}/values.csv", 'w' )
		self.LogFile.write("Time,CFUN.fun,XCBAND.band,CESQ.rsrq,CESQ.rsrp,XMONITOR.reg_status\n")
		
		
	
	
	def Execute(self, Command):
		'''Execute a system process and print the output formatted'''
		
		Result = subprocess.run( Command, capture_output=True )
		
		print_syscall( f"Command: {Command}" )
		print_status( Result.returncode )
		print_debug( f"Stdout:  {Result.stdout.decode().strip()}" )
		print_debug( f"Stderr:  {Result.stderr.decode().strip()}" )
		
		return Result
	
	
	def ExecuteBackground(self, Command):
		'''Execute a system process in background'''
		
		Result = subprocess.Popen( Command ).pid
		
		print_syscall( f"Command: {Command}" )
		print_debug( f"PID:  {Result}" )
	
	
	def Check_ETH(self):
		'''Check if a cable is plugged into the Ethernet port'''
		
		Result = self.Execute( ["cat","/sys/class/net/eth0/carrier"] )
		
		if Result.stdout.decode().strip() == '1':
			return True
		else:
			return False
	
	
	def Check_WLAN(self):
		'''Check if a wireless network is connected'''
		
		Result = self.Execute( ["iw","wlan0","link"] )
		
		if Result.stdout.decode().startswith("Connected to"):
			return True
		else:
			return False
	
	
	def Check_Connection(self):
		'''Todo: check if internet connection is available'''
		
		# Todo: check unabhängig vom Interface
		pass
	
	
	def PPPD_on(self):
		'''Start PPP daemon'''
		
		self.ExecuteBackground( ["sudo","pon","undock"] )   # Todo: wird aktiv = nicht im Hintergrund ausgeführt
	
	
	def PPPD_off(self):
		'''Stop PPP daemon'''
		
		self.ExecuteBackground( ["sudo","poff","undock"] )   # Todo: wird aktiv = nicht im Hintergrund ausgeführt
	
	
	def NetworkManager_restart(self):  # restore DNS
		'''Reload network-manager (e.g. to reload DNS after change of interface)'''
		
		self.Execute( ["sudo","systemctl","restart","NetworkManager"] )
	
	
	def Start(self):
		'''Start the connection-manager'''
		
		print("Enable via GPIO")
		self.Pins.Toggle( 'RST', 0 )  # will be replaced
		self.Pins.Set( 'EN', 0 )
		
		time.sleep(1)
		
		self.Modem.ClearBuffer()
		
		self.LastStart= time.time()
	
	
	def Restart(self):
		'''Restart the modem'''
		
		if( (time.time() - self.LastStart) > 600 ):
			self.Start()
	
	
	def ReinitUART(self):
		'''Check if UART is still responding, reinit if not'''
		
		if not self.Modem.CheckUART():
			self.Restart()
	
	
	def Run(self):
		'''Main task, perform cyclic check of the connections'''
		
		while not self.Shutdown:
			
			print("Run...")
			
			if self.Check_ETH() and False:  # removed for testing
				print("Ethernet connected")
				
				if self.Modem.State != "Off":
					self.PPPD_off()
					self.Modem.PPP_off()          # Todo: state-machine, sodass nicht x-fach hintereinander hoch/runtergefahren wird
					self.Modem.Off()
					
					self.Modem.State= "Off"
					
					self.NetworkManager_restart()
				
			elif self.Check_WLAN():
				print("WLAN connected")
				
				if self.Modem.State != "Off":
					self.PPPD_off()
					self.Modem.PPP_off()
					self.Modem.Off()
					
					self.Modem.State= "Off"
					
					self.NetworkManager_restart()
				
			else:
				print("Neither eth nor wlan connection --> ppp")
				
				self.ReinitUART()
				
				if self.Modem.State != "On":   # Todo: no restart if eth or wlan never connected ?
					self.Modem.Config()
					self.Modem.On()
#					self.Modem.PPP_on()
					
					self.Modem.State= "On"
				
				self.Modem.ClearBuffer()   # clear output of startup
				
				# Todo: in obere state-logik einbauen
				self.Modem.CheckMode()
				
				for test in range(1000):
					
					os.system('clear')
					self.Modem.DiagDecode( self.LogFile )
					
#					Status = self.Modem.PPP_check()
#					
#					if (Status[0] == '1') and (Status[1] == '1'):     # running and connected
#						pass    # check DNS ?
#					if (Status[0] == '1') and (Status[1] == '0'):     # running but not connected
#						self.PPPD_on()
#						time.sleep(5)   #wait to not reperform check immediately
#					else:                                             # not running
#						time.sleep(5)
					
					time.sleep(1)
					
					if self.Shutdown:   # Todo: zu selten aufgerufen, RX timeout = 300ms
						break
				
				print(colored("\n\n\nJob done\n\n", 'green'))
				
				while not self.Shutdown:
					time.sleep(0.1)
				
			
			# Todo: komplexer, z.b. State + TargetState kombination ?  (aktuell wird auch neu gestartet wenn alles gut ist), Frage: wann einen hard-reset (über GPIO) triggern?
			
			#time.sleep(1)
	
	
	def Stop(self, signum, frame):
		'''Stop the connection-manager'''
		
		self.Shutdown= True
		
		print("Send shutdown command")
		self.Modem.Off()
		time.sleep(0.01)
		
#		self.PPPD_off()
		
		self.Modem.Close()
		
		print("Disable via GPIO")
		self.Pins.Set( 'EN', 0 )
		
		print("Close logfile")
		self.LogFile.close()
		
		print("Shutdown")




if __name__ == "__main__":
	
	Con= ConnectionManager()
	signal.signal(signal.SIGINT, Con.Stop)    # Shutdown
	signal.signal(signal.SIGTERM, Con.Stop)   # Keyboard
	
	Con.Start()
	Con.Run()





