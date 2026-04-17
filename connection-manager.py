#!/usr/bin/python3 -u

import os
import re
import sys
import time
import serial
import signal
import argparse
import subprocess

from termcolor import colored


# Zusätzliche argumente:
# GPIO: für sinnvolle verwendung --at müsste hier mehr flexibilität rein, EN korrekt einarbeiten, '--gpios' argument ev. überhautp aufteilen in 2 (en, rst)


parser = argparse.ArgumentParser(description='Undock Connection-Manager')
parser.add_argument('-v', '--version', action='version', version='1.0')

parser.add_argument('-d', metavar="DEVICE",   help="UART device", default= 'ttySOFT0')
parser.add_argument('-b', metavar="BAUDRATE", help="UART daudrate", type=int, default= 4800)

parser.add_argument('-lte',   help="Connect via LTE-M",  action='store_true')
parser.add_argument('-nbiot', help="Connect via NB-IoT", action='store_true')

#parser.add_argument('-fallback', help="Connect only when neither ETH nor WLAN available", action='store_true')  # sollte mit der pppd config zusammenpassen, insb. sollt die nicht-fallback version wohl replacedefaultroute enthalten (welche nicht ersetzt sondern in diesem fall hinzufügt)
#	# Todo: könnte die ssh option dann ganz entfallen lassen                                                         # aktuell also "-config undock-force"  --> nicht mehr, ersetzt

parser.add_argument('-config', metavar="NAME", help="PPPD configuration file", default= 'undock')

parser.add_argument('--at', metavar="COMMAND", help="Send an AT command to the modem (and exit)")
parser.add_argument('--gpios', help="Use special GPIO behaviour", action='store_true')     # , choices=['OnOnly','DontChange'])  # on_only, dont_change ?  no_reset, keep_running , .. ?
	# Todo: EN = DIS auch einbauen? braucht ein default-value handling um nicht auch zum reset zu führen

parser.add_argument('--trace', help="Enable modem traces", action='store_true')

parser.add_argument('--human', help="Print human readable", action='store_true')
parser.add_argument('--mosh',  help="Use MOSH modem software [experimental]",     action='store_true')
parser.add_argument('--hosts', help="Correct static host entries [experimental]", action='store_true')
parser.add_argument('--ssh',   help="Ignore Ethernet connection",  action='store_true')


parser.add_argument('--firmware',    metavar="URL", help="Test firmware update [experimental]",    nargs='?', const= "http://embacher.pythonanywhere.com/terminal-modem/v3.0-fota/modem.bin")
parser.add_argument('--application', metavar="URL", help="Test application update [experimental]", nargs='?', const= "http://embacher.pythonanywhere.com/terminal-modem/v3.0-fota/application.bin")

parser.add_argument('--versions',    help="Read versions and exit", action='store_true')
parser.add_argument('--revert',      help="Revert FOTA update", action='store_true')

args = parser.parse_args()


if args.mosh:
	print("Attention: some commands are not working with MOSH target application")



# Todo: nochmal überdenken welche Ausgaben jetzt alle nur mehr unter args.human gemacht werden sollen


class printer(object):
	
	@staticmethod
	def normal(message):
		print(message)
	
	@staticmethod
	def todo(message):
		if args.human:
			print(colored(message, 'yellow'))
		else:
			print(message)
	
	@staticmethod
	def ok(message):
		if args.human:
			print(colored(message, 'green'))
		else:
			print(message)
	
	@staticmethod
	def error(message):
		if args.human:
			print(colored(message, 'red', attrs=["bold", "blink"]))
		else:
			print(message)
	
	@staticmethod
	def syscall(message):
		if args.human:
			print(colored(message, 'cyan'))
		else:
			print(message)
	
	@staticmethod
	def debug(message):
		if args.human:
			print(colored(message, 'magenta'))
	
	@staticmethod
	def status(value):
		message= f"Status:  {value}"
		if value == 0:
			printer.ok(message)
		else:
			printer.error(message)
	
	@staticmethod
	def decode(message):
		if args.human:
			print(message)
		else:
			print(message)
	
	@staticmethod
	def decode_ok(message):
		if args.human:
			print(colored(message, 'green'))
		else:
			print(message)
	
	@staticmethod
	def decode_nok(message):
		if args.human:
			print(colored(message, 'red'))
		else:
			print(message)
	
	@staticmethod
	def modem_tx(message):
		if args.human:
			print("========================  TX  ========================\n  ", end="")
			print(message.strip().replace('\n','\n  '))
			print("======================================================")
	
	@staticmethod
	def modem_rx(message):
		if args.human:
			print("------------------------  RX  ------------------------\n  ", end="")
			print(message.strip().replace('\r\n\r\n','\r\n').replace('\n','\n  '))
			print("------------------------------------------------------")
	
	@staticmethod
	def ppp(message):  # will be removed
		if args.human:
			print(colored(message, 'yellow', attrs=["bold", "blink"]))
		else:
			print(message)
	
	@staticmethod
	def dns(message):  # will be removed
		if args.human:
			print(colored(message, 'green', attrs=["bold", "blink"]))
		else:
			print(message)
	



def Execute(Command, Silent=False):
	'''Execute a system process and print the output formatted'''
	
	Result = subprocess.run( Command, capture_output=True )
	
	if not Silent:
		printer.syscall( f"Command: {Command}" )
		printer.status( Result.returncode )
		printer.debug( f"Stdout:  {Result.stdout.decode().strip()}" )
		printer.debug( f"Stderr:  {Result.stderr.decode().strip()}" )
	
	return Result


def ExecuteShell(Command, Silent=False):
	'''Execute a system process and print the output formatted'''
	
	Result = subprocess.run( Command, shell= True, capture_output=True )
	
	if not Silent:
		printer.syscall( f"Command: {Command}" )
		printer.status( Result.returncode )
		printer.debug( f"Stdout:  {Result.stdout.decode().strip()}" )
		printer.debug( f"Stderr:  {Result.stderr.decode().strip()}" )
	
	return Result


def ExecuteBackground(Command, Silent=False):
	'''Execute a system process in background'''
	
	Result = subprocess.Popen( Command ).pid
	
	if not Silent:
		printer.syscall( f"Command: {Command}" )
		printer.debug( f"PID:  {Result}" )
	
	return Result





# perform some checks

Version = ""
VersionPath = "/etc/debian_version"

if os.path.isfile(VersionPath):
	VersionFile = open(VersionPath,'r')
	Version = VersionFile.read().strip()
	VersionFile.close()

if Version != '12.9':  # 12.6
	printer.debug(f"Warning: not tested with debian version '{Version}'")


# PPPD

ConfigDir= '/etc/ppp/peers'
ConfigPath= os.path.join(ConfigDir, args.config)

try:
	if not os.path.isfile(ConfigPath):
		printer.error(f"PPPD configuration file not valid, please select from:\n\t{os.listdir(ConfigDir)}")
except:
	printer.normal("Check of PPPD configuration file not possible (started without sudo?)")



##
## Hardware v1
##

#   PI-Function  |  PI-Header  |  nRF-Pin  |  nRF-Function
# -----------------------------------------------------------------
#                           PPP-Shell
#                        UART  |  UART0
# -----------------------------------------------------------------
#           RX   |   GPIO15    |  P0.29    |   TX
#           TX   |   GPIO14    |  P0.28    |   RX
# -----------------------------------------------------------------
#                            AT-Shell
#                     USB-UART |  UART1
# -----------------------------------------------------------------
#                              |  P0.1     |   TX
#                              |  P0.0     |   RX
# -----------------------------------------------------------------
#                            GPIOs 
# -----------------------------------------------------------------
#      NRF_RST   |   GPIO12    |   -       |   NRF_RST



##
## Hardware v2
##

#   PI-Function  |  PI-Header  |  nRF-Pin  |  nRF-Function
# -----------------------------------------------------------------
#                           PPP-Shell
#                        UART  |  UART0
# -----------------------------------------------------------------
#           RX   |   GPIO15    |  P0.29    |   TX
#           TX   |   GPIO14    |  P0.28    |   RX
#          CTS   |   GPIO16    |  P0.27    |   RTS
#          RTS   |   GPIO17    |  P0.26    |   CTS
# -----------------------------------------------------------------
#                            AT-Shell
#                      SW-UART |  UART1
# -----------------------------------------------------------------
#           RX   |   GPIO21    |  P0.1     |   TX
#           TX   |   GPIO20    |  P0.0     |   RX
# -----------------------------------------------------------------
#                            GPIOs 
# -----------------------------------------------------------------
#       EN_3V3   |   GPIO26    |   -       |   -
#      NRF_RST   |   GPIO12    |   -       |   NRF_RST
#    Reserve 0   |   GPIO4     |   P0.7    |   Reserve 0 / Enable
#    Reserve 1   |   GPIO18    |   P0.6    |   Reserve 1 / (CONFIG_SLM_POWER_PIN)
#    Reserve 2   |   GPIO24    |   P0.2    |   Reserve 2 / (CONFIG_SLM_INDICATE_PIN)
#    Reserve 3   |   GPIO7     |   P0.14   |   Reserve 3 / UART1 RTS
#    Reserve 4   |   GPIO6     |   P0.15   |   Reserve 4 / UART1 CTS
#    Reserve 5   |   GPIO19    |   P0.16   |   Reserve 5
# -----------------------------------------------------------------
#
# -----------------------------------------------------------------
#                 (Modem-Trace / Logging)
#                              |  UART2
# -----------------------------------------------------------------
#    Reserve 1   |   GPIO18    |   P0.6    |   TX
#    Reserve 2   |   GPIO24    |   P0.2    |   RX
# -----------------------------------------------------------------



class GPIOs(object):
	
	Outputs= {                                             # GPIO conversion:
		'RST': { 'Number': 524, 'Init': 'high' },          # cat /sys/kernel/debug/gpio
		'DIS': { 'Number': 538, 'Init': 'low'  }           # pinout
	}                     #538
	# changed from 'out' to 'high/low' to avoid initial glitch
	
	Inputs= {             # pinctrl
		'RSVD_1': -1,
		'RSVD_2': -1,
		'RSVD_3': -1,
		'RSVD_4': -1,
		'RSVD_5': -1
	}
	
	def __init__(self):
		'''Perform electrical configuration of GPIOs and init attributes'''
		
		for Pin, Attr in self.Outputs.items():
			if Attr['Number'] == -1:
				printer.debug( f"Currently not wired: '{Pin}'" )
				continue
			else:
				if not os.path.islink( f"/sys/class/gpio/gpio{Attr['Number']}" ):
					ExecuteShell( f"echo {Attr['Number']} > /sys/class/gpio/export" )
					time.sleep(0.1)
				
				ExecuteShell( f"echo '{Attr['Init']}' > /sys/class/gpio/gpio{Attr['Number']}/direction" )
	
	
	def Set(self, Name, State):
		'''Set the state of an output'''
		
		if Name in self.Outputs:
			if self.Outputs[Name]['Number'] == -1:
				printer.debug( f"Currently not wired: '{Name}'" )
				return
			if State in [0,1]:
				ExecuteShell( f"echo {State} > /sys/class/gpio/gpio{self.Outputs[Name]['Number']}/value" )
			else:
				printer.error(f"Unknown state: '{State}' ('{self.Outputs[Name]}')")
		else:
			printer.error(f"Unknown output: '{Name}'")
	
	
	def Low(self, Name):
		'''Set the state of an output to low'''
		
		self.Set( Name, 0 )
	
	
	def High(self, Name):
		'''Set the state of an output to high'''
		
		self.Set( Name, 1 )
	
	
	def Toggle(self, Name, State, Pause= 0.01):
		'''Toggle the state of an output'''
		
		self.Set( Name, State )
		time.sleep( Pause )
		self.Set( Name, (1-State) )
	
	
	def ToggleLow(self, Name):
		'''Toggle the state of an output shortly to low'''
		
		self.Toggle( Name, 0 )
	
	
	def ToggleHigh(self, Name):
		'''Toggle the state of an output shortly to high'''
		
		self.Toggle( Name, 1 )




class SerialModem(object):
	
	def __init__(self):
		'''Open the serial port and init attributes'''
		
		self.Shutdown= False
		
		Execute( ["stty","-F",f"/dev/{args.d}",f"{args.b}"] )
	#	Execute( ["stty","-F",f"/dev/{args.d}","-echo","-onlcr"] )    # HW v 1
		Execute( ["stty","-F",f"/dev/{args.d}","-echo"] )             # HW v 2
		
		self.Modem = serial.Serial( f"/dev/{args.d}", baudrate= args.b, timeout= 1 )
		
		self.ResponsePattern= {
			'XPPP': re.compile( "#XPPP: (?P<Running>0|1),(?P<Connected>0|1)", re.MULTILINE ),
			'XSIM': re.compile( "%XSIM: (?P<state>[0-9]+)(,(?P<cause>[^\r]+))?", re.MULTILINE ),
			'CFUN': re.compile( "\+CFUN: (?P<fun>[0-9]+)", re.MULTILINE ),
			'XCBAND': re.compile( "%XCBAND: (?P<band>[0-9]+)", re.MULTILINE ),
			'CESQ': re.compile( "\+CESQ: (?P<rxlev>[0-9]+),(?P<ber>[0-9]+),(?P<rscp>[0-9]+),(?P<ecno>[0-9]+),(?P<rsrq>[0-9]+),(?P<rsrp>[0-9]+)", re.MULTILINE ),
			'XMONITOR': re.compile( "%XMONITOR: (?P<reg_status>[0-9]+)(,(?P<full_name>[^,]+),(?P<short_name>[^,]+),(?P<plmn>[^,]+))?", re.MULTILINE ),
			'XSYSTEMMODE': re.compile( "%XSYSTEMMODE: (?P<LTE_M_support>[0-9]+),(?P<NB_IoT_support>[0-9]+),(?P<GNSS_support>[0-9]+),(?P<LTE_preference>[0-9]+)", re.MULTILINE ),
			'CGDCONT': re.compile( "\+CGDCONT: (?P<cid>[0-9]+),(?P<PDP_type>[^,]+),(?P<APN>[^,]+),(?P<PDP_addr>[^,]+),(?P<d_comp>[^,]+),(?P<h_comp>[^\r]+)?", re.MULTILINE ),
			'CGCONTRDP': re.compile( "\+CGCONTRDP: (?P<cid>[0-9]+),(?P<bearer_id>[^,]*),(?P<apn>[^,]+)(,(?P<local_addr>[^,]+)(,(?P<gw_addr>[^,]+)(,(?P<DNS_prim_addr>[^,]+)(,(?P<DNS_sec_addr>[^,]+)(,,,,,(?P<IPv4_MTU>[^\r]+))?)?)?)?)?", re.MULTILINE ),
			'XFOTA': re.compile( "#XFOTA: (?P<fota_stage>[0-9]+),(?P<fota_status>[0-9]+)(,(?P<fota_info>[0-9]+))?", re.MULTILINE ),
			'XSLMVER': re.compile( "#XSLMVER: (?P<ncs_version>[^,]+),(?P<libmodem_version>[^,]+)(,(?P<customer_version>[^\r]+))?", re.MULTILINE )
		}
	
	
	def CalcTimeout(self, length):
		'''Calculate maximun response timeout, necessary due to verry low baudrate for sw emulated UART'''
		
		return ((length*8)/args.b)+0.1
	
	
	def ClearBuffer(self):
		'''Read and print the input buffer (e.g. to clear startup messages)'''
		
		self.Modem.timeout = self.CalcTimeout(100)
		
		try:
			Response= self.Modem.read(1000).decode("utf-8").strip()
		#	Response= self.Modem.readlines().decode("utf-8").strip()
		except:
			Response= "---  No response (error)  ---"          # Todo: eigentlich kein Fehler für 'ClearBuffer'
		
		printer.modem_rx(f"{Response}")
		
		return Response
	
	
	def Send(self, Command, Receive= True):
		'''Send a message to the modem and return the response'''
		
		Response= ""
		self.Modem.timeout = self.CalcTimeout(256)   # max observed AT response ~ 100, RX buffer of sw emulated UART = 256 bytes
		
		if not Command.endswith('\n'):
			Command += '\n'
		
		if not self.Modem.isOpen():
			return ''
		
		printer.modem_tx(f"{Command}")
		self.Modem.write(Command.encode('utf-8'))
		
		if Receive:
			try:
				Response= self.Modem.read(1000).decode("utf-8").strip()
			#	Response= self.Modem.readlines().decode("utf-8").strip()
			except:
				printer.error("UART read error")
			
			printer.modem_rx(f"{Response}")
			
			return Response
		else:
			return ''
	
	
	def AtSend(self, Command, Receive= True):
		'''Send an AT command to the modem including format check'''
		
		if not Command.startswith("at ") and args.mosh:
			Command = f"at {Command}"
		
		if not Command.endswith("\r\n"):
			Command = f"{Command}\r\n"
		
		return self.Send(Command, Receive)
	
	
	def UpdateTest(self):
		'''Send an AT command to the modem to test if FOTA commands are supported by the current firmware'''
		
		self.AtSend("AT#XFOTA=?")
	
	
	def UpdatePrepare(self):
		'''Send an AT command to the modem to erase modem DFU in preparation of modem FW update'''
		
		Buffer = ""
		NewLine= False
		
		self.AtSend("AT#XFOTA=9", False)
		
		self.Modem.timeout = 1
		
		for Second in range(0, 180):
			
			try:
				Buffer += self.Modem.read(1000).decode("utf-8")   # readline() not used sind it will also detect timeout as newline
			except:
				printer.error("UART read error")
				return
			
			Response= ""
			if '\n' in Buffer:
				Response, Buffer = Buffer.split('\n',1)              # more than one response may be included in the buffer, or only a part of it
			
			Response = Response.strip()  # \r
			
			if Response == '':
				print('.',end='')
				NewLine= True
			else:
				if NewLine:
					print('')
					NewLine= False
				
				print(Response)
				
				if Response.strip() == 'OK':
					break
			
			if self.Shutdown:
				break
		
		if NewLine:
			print('')
	
	
	def UpdateApplication(self, url):
		'''Send an AT command to the modem to start an application update'''
		
		if url.startswith('http://'):
			self.AtSend(f'AT#XFOTA=1,"{url}"', False)
			self.UpdateRunning( Type= "Application" )
		else:
			printer.error(f"URL for application update not supported: '{url}'")
	
	
	def UpdateModemDelta(self, url):
		'''Send an AT command to the modem to start a modem delta update'''
		
		if url.startswith('http://'):
			self.AtSend(f'AT#XFOTA=2,"{url}"', False)
			self.UpdateRunning( Type= "Modem" )
		else:
			printer.error(f"URL for modem update not supported: '{url}'")
	
	
	def UpdateModemFull(self, url):
		'''Send an AT command to the modem to start a full modem update'''
		
		if url.startswith('http://'):
			self.AtSend(f'AT#XFOTA=3,"{url}"', False)
			self.UpdateRunning( Type= "Modem" )
		else:
			printer.error(f"URL for modem update not supported: '{url}'")
	
	
	def UpdateModemStop(self):
		'''Send an AT command to the modem to stop (or pause) the current FOTA download'''
		
		self.AtSend("AT#XFOTA=0")
	
	
	def UpdateRunning(self, Type, timeout= 10):
		'''Wait for and print unsolicited notifications after update start (experimental)'''
		
		Buffer = ""
		Success= False
		NewLine= False
		
		self.Modem.timeout = 1
		
		for Second in range(0, (timeout*60)):
			
			try:
				Buffer += self.Modem.read(1000).decode("utf-8")   # readline() not used sind it will also detect timeout as newline
			except:
				printer.error("UART read error")
				return
			
			Response= ""
			if '\n' in Buffer:
				Response, Buffer = Buffer.split('\n',1)              # more than one response may be included in the buffer, or only a part of it
			
			Response = Response.strip()  # \r
			
			if Response == '':
				print('.',end='')
				NewLine= True
			else:
				if NewLine:
					print('')
					NewLine= False
				
				Result= self.ResponsePattern['XFOTA'].search(Response)
				if Result:
					# Decode
					if Result.group('fota_stage') == '0': printer.decode_ok("XFOTA.fota_stage= 0 -> 'Init'")            # Todo: welche Werte sind alle im Sinne von 'es muss nicht mehr weiter gewartet werden' zu verstehen?
					if Result.group('fota_stage') == '1': printer.decode_ok("XFOTA.fota_stage= 1 -> 'Download'")
					if Result.group('fota_stage') == '2': printer.decode_ok("XFOTA.fota_stage= 2 -> 'Download, erase pending'")
					if Result.group('fota_stage') == '3': printer.decode_ok("XFOTA.fota_stage= 3 -> 'Download, erase complete'")
					if Result.group('fota_stage') == '4': printer.decode_ok("XFOTA.fota_stage= 4 -> 'Downloaded, to be activated'")
					if Result.group('fota_stage') == '5': printer.decode_ok("XFOTA.fota_stage= 5 -> 'Complete'")
					
					if Result.group('fota_status') == '0': printer.decode_ok ("XFOTA.fota_status= 0 -> 'OK'")
					if Result.group('fota_status') == '1': printer.decode_nok("XFOTA.fota_status= 1 -> 'Error'")
					if Result.group('fota_status') == '2': printer.decode_nok("XFOTA.fota_status= 2 -> 'Cancelled'")
					if Result.group('fota_status') == '3': printer.decode_nok("XFOTA.fota_status= 3 -> 'Reverted'")
					
					if Result.group('fota_info') is not None:
						
						if Result.group('fota_status') == '0':
							printer.decode(f"XFOTA.fota_info= {Result.group('fota_info')} -> '{Result.group('fota_info')} % downloaded'")
						
						if Result.group('fota_status') == '1':
							if Result.group('fota_info') == '1': printer.decode_nok("XFOTA.fota_info= 1 -> 'Download failed'")
							if Result.group('fota_info') == '2': printer.decode_nok("XFOTA.fota_info= 2 -> 'Update image rejected'")
							if Result.group('fota_info') == '3': printer.decode_nok("XFOTA.fota_info= 3 -> 'Update image missmatch'")
							
							if Result.group('fota_info') == '71303169': printer.decode_nok("XFOTA.fota_info= 71303169 -> 'NRF_MODEM_DFU_RESULT_INTERNAL_ERROR'")
							if Result.group('fota_info') == '71303170': printer.decode_nok("XFOTA.fota_info= 71303170 -> 'NRF_MODEM_DFU_RESULT_HARDWARE_ERROR'")
							if Result.group('fota_info') == '71303171': printer.decode_nok("XFOTA.fota_info= 71303171 -> 'NRF_MODEM_DFU_RESULT_AUTH_ERROR'")
							if Result.group('fota_info') == '71303172': printer.decode_nok("XFOTA.fota_info= 71303172 -> 'NRF_MODEM_DFU_RESULT_UUID_ERROR'")
							if Result.group('fota_info') == '71303173': printer.decode_nok("XFOTA.fota_info= 71303173 -> 'NRF_MODEM_DFU_RESULT_VOLTAGE_LOW'")
					
					# Check required actions
					if Result.group('fota_stage') == '4':
						if Type == "Modem":
							self.ModemReset(False)
						else:
							self.SoftReset(False)
					
					if Result.group('fota_stage') == '5':
						Success= True
						break
					
					if Result.group('fota_status') in ['1','2','3']:
						break
					
				elif Response in ['OK','Ready']:
					printer.ok(f"XFOTA: {Response}")
				else:
					printer.error(f"Format error XFOTA:\n{Response}")
			
			if self.Shutdown:
				break
		
		
		if Buffer != "":
			printer.decode(Buffer)
		
		if not Success:
			if Type == "Modem":
				self.UpdateModemStop()   # Todo: muss wohl nur für echtes stop ausgeführt werden, nicht nach 'error' (gibt sonst einfach nochmal ERROR zurück)
	#
	#	Todo: XMODEMRESET?
	
	
	
	
	def Config(self):
		'''Send AT commands to the modem to configure APN and bandlock'''
		
		self.AtSend('AT%XBANDLOCK=2,"10000000000010000000"')    # 8 and 20
#		self.AtSend('AT+CGDCONT=0,"IPV4V6","m2m.public.at"')    # internet.t-mobile.at, business.gprsinternet, m2m.public.at
#		self.AtSend('AT+COPS=1,2,"23203",7')                    # Manual network selection, Magenta, E-UTRAN
		
		if args.lte and not args.nbiot:
			self.AtSend("AT%XSYSTEMMODE=1,0,0,0")
		elif args.nbiot and not args.lte:
			self.AtSend("AT%XSYSTEMMODE=0,1,0,0")
		else:
			self.AtSend("AT%XSYSTEMMODE=1,1,0,1")  # LTE preferred
		
		if args.trace:
			self.AtSend("AT%XMODEMTRACE=1,2")
		
		# Test:
		#self.AtSend('AT%XEPCO=0')  # disable ePCO to solve DNS issues

	
	
	def On(self):
		'''Send an AT command to the modem to set "functional mode 1" (full functionality)'''
		
		self.AtSend("AT+CFUN=1")
	
	
	def Off(self):
		'''Send an AT command to the modem to set "functional mode 0" (minimum functionality)'''
		
		self.AtSend("AT+CFUN=0")
		
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
		Result = self.ResponsePattern['XPPP'].search(Response)
		
		if Result:
			printer.todo( f"Running: {Result.group('Running')}, Connected: {Result.group('Connected')}" )
			return { 'Running': Result.group('Running'), 'Connected': Result.group('Connected') }
		else:
			return { 'Running': '0', 'Connected': '0' }
	
	
	def Sleep(self):
		'''Send an AT command to the modem to enter sleep mode'''
		
		self.AtSend("AT#XSLEEP=1")
	
	
	def Idle(self):
		'''Send an AT command to the modem to enter idle mode'''
		
		self.AtSend("AT#XSLEEP=2")
	
	
	def Shutdown(self):
		'''Send an AT command to the modem to enter shutdown'''
		
		self.AtSend("AT#XSHUTDOWN")
	
	
	def SoftReset(self, Receive= True):
		'''Send an AT command to the modem to perform a soft reset'''
		
		self.AtSend("AT#XRESET", Receive)
	
	
	def ModemReset(self, Receive= True):
		'''Send an AT command to the modem to perform a soft reset'''
		
		self.AtSend("AT#XMODEMRESET", Receive)
	
	
	def FlightMode(self):
		'''Send an AT command to the modem to set "functional mode 4" (flight mode)'''
		
		self.AtSend("AT+CFUN=4")
	
	
	def CheckMode(self):
		'''Check if mode is set to 'normal', e.g. reinit after press of reset button'''
		
		Response = self.AtSend("AT+CFUN?")
		Result= self.ResponsePattern['CFUN'].search(Response)
		if Result:
			if Result.group('fun') ==  '0':
				printer.decode_nok("CFUN.fun= 0 -> 'Minimum functionality mode' -> set on")
				self.On()
		else:
			printer.error(f"Format error 'AT+CFUN?':\n{Response}")
	
	
	def CheckUART(self):
		'''Check if UART is still responding'''
		
		self.ClearBuffer()
		
		Response = self.AtSend("AT+CGSN")
		if Response == "":
			return False
		else:
			return True
	
	
#	def Diag(self):
#		'''Send several AT command to the modem to get diagnostic information'''
#		
#		self.AtSend("AT+CFUN?")
#		self.AtSend("AT+CESQ")
#		self.AtSend("AT%XMONITOR")
#		self.AtSend("AT%XCBAND")
#		self.AtSend("AT%XSYSTEMMODE?")
	
	
	def DiagBase(self):
		'''Send some dianostic commands to the modem and decode the response'''
		
		self.AtSend("AT+CGMM")   # Todo: check versions ?
		self.AtSend("AT+CGMR")
		self.AtSend("AT+CGSN")
		
		self.AtSend("AT%SHORTSWVER")
		self.AtSend("AT%HWVERSION")
		
	#	self.AtSend('AT#XSLMVER')
		
		Response = self.AtSend("AT#XSLMVER")
		Result= self.ResponsePattern['XSLMVER'].search(Response)
		if Result:
			if Result.group('ncs_version') == '"2.9.0"':
				printer.decode(f"XSLMVER.ncs_version= {Result.group('ncs_version')}")
			else:
				printer.decode_nok(f"XSLMVER.ncs_version= {Result.group('ncs_version')}")
			
			printer.decode(f"XSLMVER.libmodem_version= {Result.group('libmodem_version')}")
			
			if Result.group('customer_version') == '"Undock_v3.0"':
				printer.decode_ok(f"XSLMVER.customer_version= {Result.group('customer_version')}")
			else:
				printer.decode_nok(f"XSLMVER.customer_version= {Result.group('customer_version')}")
		
		Response = self.AtSend("AT%XSYSTEMMODE?")
		Result= self.ResponsePattern['XSYSTEMMODE'].search(Response)
		if Result:
			if args.lte or (not args.lte and not args.nbiot):
				if Result.group('LTE_M_support') == '0': printer.decode_nok("XSYSTEMMODE.LTE_M_support= 0 -> 'LTE-M not supported'")
				if Result.group('LTE_M_support') == '1': printer.decode_ok ("XSYSTEMMODE.LTE_M_support= 1 -> 'LTE-M supported'")
			else:
				if Result.group('LTE_M_support') == '0': printer.decode    ("XSYSTEMMODE.LTE_M_support= 0 -> 'LTE-M not supported'")
				if Result.group('LTE_M_support') == '1': printer.decode_nok("XSYSTEMMODE.LTE_M_support= 1 -> 'LTE-M supported'")
			
			if args.nbiot or (not args.lte and not args.nbiot):
				if Result.group('NB_IoT_support') == '0': printer.decode_nok("XSYSTEMMODE.NB_IoT_support= 0 -> 'NB-IoT not supported'")
				if Result.group('NB_IoT_support') == '1': printer.decode_ok ("XSYSTEMMODE.NB_IoT_support= 1 -> 'NB-IoT supported'")
			else:
				if Result.group('NB_IoT_support') == '0': printer.decode    ("XSYSTEMMODE.NB_IoT_support= 0 -> 'NB-IoT not supported'")
				if Result.group('NB_IoT_support') == '1': printer.decode_nok("XSYSTEMMODE.NB_IoT_support= 1 -> 'NB-IoT supported'")
			
			if Result.group('GNSS_support') == '0': printer.decode("XSYSTEMMODE.GNSS_support= 0 -> 'GNSS not supported'")
			if Result.group('GNSS_support') == '1': printer.decode("XSYSTEMMODE.GNSS_support= 1 -> 'GNSS supported'")
			
			if Result.group('LTE_preference') == '0': printer.decode("XSYSTEMMODE.LTE_preference= 0 -> 'No preference'")
			if Result.group('LTE_preference') == '1': printer.decode("XSYSTEMMODE.LTE_preference= 1 -> 'LTE-M preferred'")
			if Result.group('LTE_preference') == '2': printer.decode("XSYSTEMMODE.LTE_preference= 2 -> 'NB-IoT preferred'")
			if Result.group('LTE_preference') == '3': printer.decode("XSYSTEMMODE.LTE_preference= 3 -> 'Priority from network (LTE-M)'")
			if Result.group('LTE_preference') == '4': printer.decode("XSYSTEMMODE.LTE_preference= 4 -> 'Priority from network (NB-IoT)'")
		else:
			printer.error(f"Format error 'AT%XSYSTEMMODE?':\n{Response}")
		
	
	def DiagConnection(self):
		'''Send some dianostic commands to the modem and decode the response'''
		
		Response = self.AtSend("AT%XSIM?")
		Result= self.ResponsePattern['XSIM'].search(Response)
		if Result:
			if Result.group('state') == '0': printer.decode_nok("XSIM.state= 0 -> 'UICC not initialized'")
			if Result.group('state') == '1': printer.decode_ok ("XSIM.state= 1 -> 'UICC initialization OK'")
			
			if Result.group('cause') is not None:
				if Result.group('cause') ==  '1': printer.decode_nok("XSIM.cause= 1 -> 'PIN required'")
				if Result.group('cause') ==  '2': printer.decode_nok("XSIM.cause= 2 -> 'PIN2 required'")
				if Result.group('cause') ==  '3': printer.decode_nok("XSIM.cause= 3 -> 'PUK required (PIN blocked)'")
				if Result.group('cause') ==  '4': printer.decode_nok("XSIM.cause= 4 -> 'PUK2 required (PIN2 blocked)'")
				if Result.group('cause') ==  '5': printer.decode_nok("XSIM.cause= 5 -> 'PUK blocked'")
				if Result.group('cause') ==  '6': printer.decode_nok("XSIM.cause= 6 -> 'PUK2 blocked'")
				if Result.group('cause') ==  '7': printer.decode_nok("XSIM.cause= 7 -> 'Device personalization blocked'")
				if Result.group('cause') ==  '8': printer.decode_nok("XSIM.cause= 8 -> 'IMEI lock blocked'")
				if Result.group('cause') ==  '9': printer.decode_nok("XSIM.cause= 9 -> 'USIM card failure'")
				if Result.group('cause') == '10': printer.decode_nok("XSIM.cause= 10 -> 'USIM card changed'")
				if Result.group('cause') == '11': printer.decode_nok("XSIM.cause= 11 -> 'USIM profile changed'")
				if Result.group('cause') == '12': printer.decode_nok("XSIM.cause= 12 -> 'GNSS mode only (UICC not initialized)'")
		else:
			printer.error(f"Format error 'AT%XSIM?':\n{Response}")
		
		Response = self.AtSend("AT+CFUN?")
		Result= self.ResponsePattern['CFUN'].search(Response)
		if Result:
			if Result.group('fun') ==  '0': printer.decode_nok("CFUN.fun= 0 -> 'Minimum functionality mode'")
			if Result.group('fun') ==  '1': printer.decode_ok ("CFUN.fun= 1 -> 'Normal mode'")
			if Result.group('fun') ==  '2': printer.decode_nok("CFUN.fun= 2 -> 'Receive only mode'")
			if Result.group('fun') ==  '4': printer.decode_nok("CFUN.fun= 4 -> 'Flight mode'")
			if Result.group('fun') == '21': printer.decode_nok("CFUN.fun= 21 -> 'LTE is activated'")
			if Result.group('fun') == '31': printer.decode_nok("CFUN.fun= 31 -> 'GNSS is activated'")
			if Result.group('fun') == '41': printer.decode_nok("CFUN.fun= 41 -> 'UICC is activated'")
		else:
			printer.error(f"Format error 'AT+CFUN?':\n{Response}")
		
		Response = self.AtSend("AT%XCBAND")
		Result= self.ResponsePattern['XCBAND'].search(Response)
		if Result:
			if Result.group('band') == '0':
				printer.decode_nok("XCBAND.band= 0 -> 'Current information not available'")
			else:
				printer.decode_ok(f"XCBAND.band= {Result.group('band')}")
		else:
			printer.error(f"Format error 'AT%XCBAND':\n{Response}")
		
		Response = self.AtSend("AT+CESQ")
		Result= self.ResponsePattern['CESQ'].search(Response)
		if Result:
			if Result.group('rsrq') == '255':
				printer.decode_nok("CESQ.rsrq= 255 -> 'Not known or not detectable'")
			else:
				printer.decode_ok(f"CESQ.rsrq= {Result.group('rsrq')}")
			
			if Result.group('rsrp') == '255':
				printer.decode_nok("CESQ.rsrp= 255 -> 'Not known or not detectable'")
			else:
				printer.decode_ok(f"CESQ.rsrp= {Result.group('rsrp')}")
		else:
			printer.error(f"Format error 'AT+CESQ':\n{Response}")
		
		Response = self.AtSend("AT%XMONITOR")
		Result= self.ResponsePattern['XMONITOR'].search(Response)
		if Result:
			if Result.group('reg_status') ==  '0': printer.decode_nok("XMONITOR.reg_status= 0 -> 'Not registered, not currently searching'")
			if Result.group('reg_status') ==  '1': printer.decode_ok ("XMONITOR.reg_status= 1 -> 'Registered, home network'")
			if Result.group('reg_status') ==  '2': printer.decode_nok("XMONITOR.reg_status= 2 -> 'Not registered, currently searching'")
			if Result.group('reg_status') ==  '3': printer.decode_nok("XMONITOR.reg_status= 3 -> 'Registration denied'")
			if Result.group('reg_status') ==  '4': printer.decode_nok("XMONITOR.reg_status= 4 -> 'Unknown'")
			if Result.group('reg_status') ==  '5': printer.decode_ok ("XMONITOR.reg_status= 5 -> 'Registered, roaming'")
			if Result.group('reg_status') == '90': printer.decode_nok("XMONITOR.reg_status= 90 -> 'Not registered due to failure'")
			
			if Result.group('full_name') is not None:
				printer.decode_ok(f"XMONITOR.full_name= {Result.group('full_name')}")
			
			if Result.group('short_name') is not None:
				printer.decode_ok(f"XMONITOR.short_name= {Result.group('short_name')}")
			
			if Result.group('plmn') is not None:
				printer.decode_ok(f"XMONITOR.plmn= {Result.group('plmn')}")
		else:
			printer.error(f"Format error 'AT%XMONITOR':\n{Response}")
		
		Response = self.AtSend("AT+CGDCONT?")
		Result= self.ResponsePattern['CGDCONT'].search(Response)
		if Result:
			printer.decode(f"CGDCONT.cid= {Result.group('cid')}")
			printer.decode(f"CGDCONT.PDP_type= {Result.group('PDP_type')}")
			printer.decode(f"CGDCONT.APN= {Result.group('APN')}")
			printer.decode(f"CGDCONT.PDP_addr= {Result.group('PDP_addr')}")
		else:
			printer.error(f"Format error 'AT+CGDCONT?':\n{Response}")
		
		Response = self.AtSend("AT+CGCONTRDP=0")   # Todo: 0-10 ?
		if Response.strip() == 'OK':
			printer.decode("No context available")
		else:
			if '\n' in Response:
				Response, ResponseIPv6 = Response.split('\n',1)
			Result= self.ResponsePattern['CGCONTRDP'].search(Response)
			if Result:
				printer.decode(f"CGCONTRDP.cid= {Result.group('cid')}")
				printer.decode(f"CGCONTRDP.bearer_id= {Result.group('bearer_id')}")
				printer.decode(f"CGCONTRDP.apn= {Result.group('apn')}")
				printer.decode(f"CGCONTRDP.local_addr= {Result.group('local_addr')}")
				printer.decode(f"CGCONTRDP.gw_addr= {Result.group('gw_addr')}")
				printer.dns   (f"CGCONTRDP.DNS_prim_addr= {Result.group('DNS_prim_addr')}") # test only: dns->decode
				printer.dns   (f"CGCONTRDP.DNS_sec_addr= {Result.group('DNS_sec_addr')}")
				printer.decode(f"CGCONTRDP.IPv4_MTU= {Result.group('IPv4_MTU')}")
			else:
				printer.error(f"Format error 'AT+CGDCONT?':\n{Response}")
	
	
	def Diag(self):
		'''Send some dianostic commands to the modem and decode the response'''
		
		self.DiagBase()
		self.DiagConnection()
	
	
	def Close(self):
		'''Close the serial port'''
		
		self.Modem.close()



class ConnectionManager(object):
	
	def __init__(self):
		'''Configure and open the serial port, init GPIOs, init attributes'''
		
		self.Shutdown= False
		self.LastStart= time.time()
		
		self.Pattern= {
			'Hosts': re.compile( "^(?P<Address>[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})\s+(?P<Name>.+)$" )
		}
		
		self.ReinitUART()
		
		printer.normal("Init serial console")
		self.Modem = SerialModem()
		
		printer.normal("Init GPIOs")
		self.Pins = GPIOs()
	
	
	def wait(self, pause):
		'''Wait a defined time, but shorten it in case of a shutdown'''
		
		for x in range(0,int(pause*100)):
			time.sleep(0.01)
			if self.Shutdown:
				break
	
	
	def Check_ETH(self, Silent=False):
		'''Check if a cable is plugged into the Ethernet port'''
		
		Result = Execute( ["cat","/sys/class/net/eth0/carrier"], Silent )
		
		if Result.stdout.decode().strip() == '1' and not args.ssh:
			return True
		else:
			return False
	
	
	def Check_WLAN(self, Silent=False):
		'''Check if a wireless network is connected'''
		
		Result = Execute( ["iw","wlan0","link"], Silent )
		
		if Result.stdout.decode().startswith("Connected to"):
			return True
		else:
			return False
	
	def Check_NonModem(self, Silent=False):
		'''Check if a cable is plugged into the Ethernet port or if a wireless network is connected'''
		
		if self.Check_ETH(Silent):
			return True
		elif self.Check_WLAN(Silent):
			return True
		else:
			return False
		
	
	def Check_Connection(self):
		'''Check if internet connection is available'''
		
		Result = Execute( ["ping","8.8.8.8","-c","1"] )
		
		if "100% packet loss" in Result.stdout.decode():
			return False
		else:
			return True
	
	
	def Check_DNS(self):
		'''Check if DNS is working'''
		
		Result = Execute( ["ping","google.com","-c","1"] )
		
		if "100% packet loss" in Result.stdout.decode():
			return False
		else:
			return True
	
	
	def PPPD_on(self):
		'''Start PPP daemon'''
		
		ExecuteBackground( ["sudo","pon",args.config] )
	
	
	def PPPD_off(self):
		'''Stop PPP daemon'''
		
		ExecuteBackground( ["sudo","poff",args.config] )
	
	
	def NetworkManager_restart(self):
		'''Reload network-manager (e.g. to reload DNS after change of interface)'''
		
		Execute( ["sudo","systemctl","restart","NetworkManager"] )
	
	
	def Start(self):
		'''Start the connection-manager'''
		
		# Changed from EN + RST to combined version to not produce 2 resets at startup
		
		
		printer.normal("Enable/Reset via GPIO")   # Todo: eigentlich sind dass dann gleich zwei resets fürs Modem ?!
		
		if args.gpios is not None:
			self.Pins.High('RST')
		
		self.Pins.Low('DIS')   # Todo: überarbeiten, ist jetzt schon im init auf default low (Konzept ändern, sodass kein init gemacht wird und dann immer über direction zugreifen?)
		
		if args.gpios is not None:
			self.Pins.Low('RST')
		
		self.wait(5)
		
		self.Modem.Config()   # Todo: falls das gewünscht wäre so wäre es hier wohl noch zu früh, macht Fehler --> schaut so aus als macht einfach immer das erste RX einen Fehler
		
		self.LastStart= time.time()
	
	
	def Restart(self):
		'''Restart the modem'''
		
		if (time.time() - self.LastStart) > (30*60):
			self.Start()
		else:
			printer.error("Restart omitted due to 'Modem Reset Loop Restriction'")
	
	
	def RestartCheck(self):
		'''Check if UART is still responding, reinit if not'''
		
		if not self.Modem.CheckUART():
			self.Restart()
	
	
	def ReinitUART(self):
		'''Re-Init SW UART'''
		
		Execute( ["sudo","rmmod","soft_uart"] )
		time.sleep(1)
		Execute( ["sudo","insmod","/etc/undock/soft_uart/soft_uart.ko","gpio_tx=532","gpio_rx=533"] )
		time.sleep(1)
	
	
	def Update(self):
		'''Trigger FOTA update'''
		
		self.Modem.PPP_off()   # Todo: braucht sehr lange für die Antwort, eventuell ähnliche Logik wie bei UpdatePrepare umsetzen
		time.sleep(10)
		
		self.Modem.UpdateTest()
		
		if args.application is not None:
			Target = args.application.strip('"')
			if args.revert:
				Target = Target.replace('-fota','')
				
			self.Modem.UpdateApplication( Target )
		
		if args.firmware is not None:
			Target = args.firmware.strip('"')
			if args.revert:
				Target = Target.replace('-fota','')
				
			self.Modem.UpdatePrepare()
			self.Modem.UpdateModemDelta( Target )
		
#		self.Modem.UpdateApplication( "http://35.173.69.207/terminal-modem/test_dfu_application/application.bin" )   # Todo: name -> IMEI
#		self.Modem.UpdateModemDelta( f"http://embacher.pythonanywhere.com/terminal-modem/delta_1.3.7_to_1.3.7-FOTA-TEST/modem" )
#		self.Modem.UpdateModemFull( f"http://embacher.pythonanywhere.com/terminal-modem/1.3.7-FOTA-TEST/modem" )

	
	
	def CheckHosts(self):
		'''Manually check DNS entries in file /etc/hosts and update if necessary'''
		
		if os.path.isfile( '/etc/hosts_backup' ):
			os.unlink( '/etc/hosts_backup' )
		
		OldHosts = open( '/etc/hosts', 'r' )
		NewHosts = open( '/etc/hosts2', 'w' )
		
		while Line := OldHosts.readline():
			
			Name = ''
			OldAddress = ''
			NewAddress = ''
			
			Result = self.Pattern['Hosts'].search(Line)
			if Result:
				Name = Result.group('Name')
				OldAddress = Result.group('Address')
				
				Lookup = Execute( ["dig","@8.8.8.8","+short",Name] )
				NewAddress = Lookup.stdout.decode().strip()              # also empty if nothing found
			
			if (NewAddress != OldAddress) and (NewAddress != ''):
				printer.dns(f"New address found for '{Name}': {OldAddress} -> {NewAddress}")
				NewHosts.write( f"{NewAddress:<20}{Name}\n" )
			else:
				NewHosts.write( f"{Line}" )
		
		OldHosts.close()
		NewHosts.close()
		
		os.rename('/etc/hosts', '/etc/hosts_backup')
		os.rename('/etc/hosts2', '/etc/hosts')
	
	
	def Run(self):
		'''Main task, perform cyclic check of the connections'''
		
		while not self.Shutdown:
			
			#printer.normal("Run...")
			
			# ===  ETH / WLAN  ===
			
			Retry = True
			while Retry:
				if self.Check_ETH():
					printer.normal("Ethernet connected")
					while self.Check_ETH( Silent= True ):
						self.wait(0.1)
					if self.Shutdown:
						return
					printer.normal("Ethernet disconnected")
				
				if self.Check_WLAN():
					printer.normal("WLAN connected")
					while self.Check_WLAN( Silent= True ):
						self.wait(0.1)
					if self.Shutdown:
						return
					printer.normal("WLAN disconnected")
				else:
					Retry = False    # WLAN may be connected for a long time, so it makes sense to re-check ETH afterwards
			
			
			# ===  Modem  ===
			
			# connect / run
			
			while True:   # 'do while'
				
				self.RestartCheck()  # may call a new 'Start'
				
				self.Modem.On()
				self.wait(1)
				
				self.Modem.DiagBase()
				self.Modem.PPP_on()
				
				for test in range(12):
					
					#os.system('clear')    # removed for debugging
					self.Modem.DiagConnection()
					
					Status = self.Modem.PPP_check()
					
					if Status['Running'] == '1':
						if Status['Connected'] == '0':
							printer.ppp("Running but not connected")
							self.PPPD_on()
						else:
							printer.ppp("Running and connected")
							self.Check_Connection()
							self.Check_DNS()
							# Todo: trigger reset after some time if no connection although 'running and connected'
					else:
						printer.ppp("Not running")
					
					self.wait(5)
					
					if self.Shutdown:
						break
					elif self.Check_NonModem():
						break
				
				if self.Shutdown:
					break;
				elif self.Check_NonModem():
					break
			
			# disconnect
			
			if not self.Shutdown:
				self.PPPD_off()
				self.Modem.PPP_off()
				self.Modem.Off()
				self.wait(1)
				
				self.NetworkManager_restart()
				self.wait(1)
	
	
	def Stop(self, signum, frame):
		'''Stop the connection-manager'''
		
		self.Shutdown= True
		self.Modem.Shutdown= True
		time.sleep(1)
		
		printer.normal("Send shutdown command")
		self.Modem.Off()
		
		printer.normal("Shutdown PPP daemon and close serial connection")
		self.PPPD_off()
		self.Modem.Close()
		
	#	if args.gpios is not None:                     # Todo: temporarily removed (debuger, ...)
	#		printer.normal("Disable via GPIO")
	#		self.Pins.High('DIS')
		
		printer.normal("Restart network manager")
		self.NetworkManager_restart()
		
		printer.normal("Shutdown")




if __name__ == "__main__":
	
	Con= ConnectionManager()
	
	if args.at is not None:
		Con.Modem.AtSend(args.at.strip('"'))
		sys.exit()
	
	if args.hosts:  # sudo
		Con.CheckHosts()
		sys.exit()
	
	
	signal.signal(signal.SIGINT, Con.Stop)    # Shutdown
	signal.signal(signal.SIGTERM, Con.Stop)   # Keyboard
	
	Con.Start()  # Also enable at startup for 'Modem Reset Loop Restriction' even though not necessary (if e.g. Ethernet is plugged in)
	
	if args.versions:
		Con.Modem.DiagBase()
		sys.exit()
	
	if args.application or args.firmware:
		
#		time.sleep(3)
#		
#		printer.todo("Test deactivation of IPv6")
#		Con.Modem.AtSend('AT+CGDCONT=0,"IP","m2m.public.at"')
		
		time.sleep(3)
		Con.Modem.DiagBase()
		time.sleep(3)
		Con.Modem.On()
		time.sleep(5)
		
		for x in range(3):
			Con.Modem.DiagConnection()
			time.sleep(5)
		
		Con.Update()
		
		time.sleep(5)
		sys.exit()
	
	Con.Run()




