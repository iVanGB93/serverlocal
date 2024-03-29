from django.core.mail.message import EmailMessage
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Recarga, Oper, EstadoServicio
from django.contrib.auth.models import User
from users.models import Profile, Notificacion
from sync.syncs import actualizacion_remota
from sync.models import EstadoConexion
from decouple import config
import xml.etree.ElementTree
import subprocess
import hashlib
import requests
import paramiko
import routeros_api
import os

from sync.actions import DynamicEmailSending

servidor = config('NOMBRE_SERVIDOR')


def crearOper(usuario, servicio, cantidad):
    userinst = User.objects.get(username=usuario)           
    nuevaOper = Oper(tipo='PAGO', usuario=userinst, servicio=servicio, cantidad=cantidad)
    nuevaOper.save()
    code = nuevaOper.code
    return code

#FILEZILLA
user_xml_fmt = '''
        <User Name="{username}">
            <Option Name="Pass">{md5_pwd}</Option>
            <Option Name="Group">{group}</Option>
            <Option Name="Bypass server userlimit">2</Option>
            <Option Name="User Limit">0</Option>
            <Option Name="IP Limit">0</Option>
            <Option Name="Enabled">2</Option>
            <Option Name="Comments" />
            <Option Name="ForceSsl">2</Option>
            <IpFilter>
                <Disallowed />
                <Allowed />
            </IpFilter>
            <Permissions />
            <SpeedLimits DlType="0" DlLimit="10" ServerDlLimitBypass="2" UlType="0" UlLimit="10" ServerUlLimitBypass="2">
                <Download />
                <Upload />
            </SpeedLimits>
        </User>
'''

folder = 'C:/Program Files (x86)/FileZilla Server'
xml_path = os.path.join(folder, 'FileZilla Server.xml')
exe_path = os.path.join(folder, 'FileZilla Server.exe')

class DDDManager():

    def __init__(self, filename):
        self.filename = filename

    def setup(self):
        self.tree = xml.etree.ElementTree.parse(self.filename)
        self.root = self.tree.getroot()
        self.user_tree = self.root.findall('Users')[0]
        return self

    def new_user(self, username, pwd, group):
        pwd = pwd
        md5_pwd = hashlib.md5(pwd.encode('utf-8')).hexdigest()
        xml_str = user_xml_fmt.format(username=username, md5_pwd=md5_pwd, group=group)
        return xml.etree.ElementTree.fromstring(xml_str)

    def add_user(self, *arg):
        user = self.new_user(*arg)        
        self.user_tree.append(user)

    def dump(self):
        self.tree.write(self.filename)

def activarFTP(username, pwd, group):

    manager = DDDManager(xml_path).setup() 

    manager.add_user(username, pwd, group)
    
    manager.dump()
    subprocess.run([exe_path, '/reload-config'], shell=True)
#Fin FILEZILLA

def conectar_mikrotik(ip, username, password, usuario, contraseña, perfil, horas):
    result = {'estado': False}
    try:
        connection = routeros_api.RouterOsApiPool(ip, username=username, password=password, plaintext_login=True)
        api = connection.get_api()
    except:
        result['mensaje'] = 'Falló la conexión con el mikrotik, intente más tarde.'
        return result
    lista_usuarios = api.get_resource('/ip/hotspot/user')
    usuario_mk = lista_usuarios.get(name=usuario)
    if horas == None:
        horas = '0'
    else:
        horas = horas
    if usuario_mk != []:
        if horas == '0':
            lista_usuarios.set(id=usuario_mk[0]['id'], password=contraseña, profile=perfil, disabled='false', limit_uptime=horas)
            result['estado'] = True
            return result
        else:
            lista_usuarios.remove(id=usuario_mk[0]['id'])
    lista_usuarios.add(name=usuario, password=contraseña, profile=perfil, limit_uptime=horas)
    result['estado'] = True
    return result
    

def comprar_internet(usuario, tipo, contra, duracion, horas, velocidad):
    result = {'correcto': False}
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result
    usuario = User.objects.get(username=usuario)
    servicio = EstadoServicio.objects.get(usuario=usuario)
    if servicio.internet == True:
        result['mensaje'] = 'Ya tiene el servicio activo.'
        return result
    profile = Profile.objects.get(usuario=usuario)
    if tipo == '24h':
        costo_base = int(config('INTERNET_PRICE_SEMANAL'))
        if duracion == 'semanal':          
            dias = 7
            if velocidad == '1mb':
                costo = costo_base
                perfil = 'usuarios_1mb_24h'
            elif velocidad == '2mb':
                costo = costo_base * 2
                perfil = 'usuarios_2mb_24h'
            elif velocidad == '3mb':
                costo = costo_base * 3
                perfil = 'usuarios_3mb_24h'
            elif velocidad == '4mb':
                costo = costo_base * 4
                perfil = 'usuarios_4mb_24h'               
        if duracion == 'mensual':            
            dias = 30
            if velocidad == '1mb':
                costo = costo_base * 4
                perfil = 'usuarios_1mb_24h'
            elif velocidad == '2mb':
                costo = costo_base * 2 * 4
                perfil = 'usuarios_2mb_24h'
            elif velocidad == '3mb':
                costo = costo_base * 3 * 4
                perfil = 'usuarios_3mb_24h'
            elif velocidad == '4mb':
                costo = costo_base * 4 * 4
                perfil = 'usuarios_4mb_24h'
        user_coins = int(profile.coins)
        if user_coins < costo:
            result['mensaje'] = f'No tiene suficientes coins, necesita { costo }, por favor recargue.'
            return result
        else:
            servicio.int_time = timezone.now() + timedelta(days=dias)
            profile.coins = profile.coins - costo
        resultado = conectar_mikrotik(config('MK1_IP'), config('MK1_USER'), config('MK1_PASSWORD'), usuario.username, contra, perfil, None)
        if resultado['estado']:    
            servicio.internet = True  
            servicio.int_tipo = 'internet-24h'
            servicio.int_duracion = duracion
            servicio.int_velocidad = velocidad
            servicio.sync = False
            servicio.save()
            profile.sync = False
            profile.save()
            notificacion = Notificacion(usuario=usuario, tipo="PAGO", contenido="Internet 24 horas activado")
            notificacion.save()
            code = crearOper(usuario.username, 'internet-24h', costo)
            end_time = servicio.int_time.strftime('%B %d, a las %H:%M ')
            data = {'to': usuario.email, 'template_id': 'd-a9864607981c4305aedaf3d5277aa19b', 'dynamicdata': {'first_name': usuario.username, 'service': 'internet', 'end_time': end_time, 'code': code}}
            DynamicEmailSending(data).start()
            result['mensaje'] = 'Servicio activado con éxito.'
            result['correcto'] = True
            return result
        else:
            result['mensaje'] = resultado['mensaje']
            return result
    elif tipo == 'horas':
        cantidad_horas = int(horas)
        if cantidad_horas <5:
            result['mensaje'] = 'Mínimo 5 horas.'
            return result
        costo_base = int(config('INTERNET_PRICE_HORAS'))
        if velocidad == '1mb':
            costo = costo_base * cantidad_horas
            perfil = 'usuarios_1mb_horas'
        elif velocidad == '2mb':
            costo = costo_base * 2 * cantidad_horas
            perfil = 'usuarios_2mb_horas'
        elif velocidad == '3mb':
            costo = costo_base * 3 * cantidad_horas
            perfil = 'usuarios_3mb_horas'
        elif velocidad == '4mb':
            costo = costo_base * 4 * cantidad_horas
            perfil = 'usuarios_4mb_horas'
        user_coins = int(profile.coins)
        if user_coins < costo:
            result['mensaje'] = f'No tiene suficientes coins, necesita { costo }, por favor recargue.'
            return result
        else:
            profile.coins = profile.coins - costo    
            horasMK = f'{horas}:00:00'
            resultado = conectar_mikrotik(config('MK1_IP'), config('MK1_USER'), config('MK1_PASSWORD'), usuario.username, contra, perfil, horasMK)
            if resultado['estado']:    
                code = crearOper(usuario.username, 'internetHoras', costo)
                servicio.internet = True
                servicio.int_horas = horas
                servicio.int_tipo = 'internetHoras'
                servicio.int_duracion = None
                servicio.int_velocidad = velocidad
                servicio.int_time = None
                servicio.sync = False
                servicio.save()
                profile.sync = False
                profile.save()
                contenido = f"Internet por { horas} horas activado"
                notificacion = Notificacion(usuario=usuario, tipo="PAGO", contenido=contenido)
                notificacion.save()
                end_time = f'que consuma sus {horas} horas'
                data = {'to': usuario.email, 'template_id': 'd-a9864607981c4305aedaf3d5277aa19b', 'dynamicdata': {'first_name': usuario.username, 'service': 'internet', 'end_time': end_time, 'code': code}}
                DynamicEmailSending(data).start()
                result['mensaje'] = 'Servicio activado con éxito.'
                result['correcto'] = True
                return result
            else:
                result['mensaje'] = resultado['mensaje']
                return result             
    else:
        result['mensaje'] = 'Error de solicitud'
        return result

def comprar_jc(usuario):
    result = {'correcto': False}
    jc_price = int(config('JC_PRICE'))
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result
    usuario = User.objects.get(username=usuario)
    servicio = EstadoServicio.objects.get(usuario=usuario.id)
    if servicio.jc == True:
        result['mensaje'] = 'Ya tiene el servicio activo.'
        return result
    if not servicio.sync:
        result['mensaje'] = 'Debe tener los servicios sincronizados para comprar.'
        return result
    profile = Profile.objects.get(usuario=usuario)
    if profile.coins >= jc_price:
        profile.coins = profile.coins - jc_price
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(config('MK2_IP'), username=config('MK2_USER'), password=config('MK2_PASSWORD'))
            stdin, stdout, stderr = client.exec_command(f'/ip firewall address-list set [find comment={usuario.username}] disable=no')
            client.close()
            profile.sync = False
            profile.save()
            servicio.jc = True
            servicio.jc_time = timezone.now() + timedelta(days=30)
            servicio.sync = False
            servicio.save()
            notificacion = Notificacion(usuario=usuario, tipo="PAGO", contenido="Joven Club activado")
            notificacion.save()
            code = crearOper(usuario.username, "Joven-Club", jc_price)
            end_time = servicio.int_time.strftime('%B %d, a las %H:%M ')
            data = {'to': usuario.email, 'template_id': 'd-a9864607981c4305aedaf3d5277aa19b', 'dynamicdata': {'first_name': usuario.username, 'service': 'Joven Club', 'end_time': end_time, 'code': code}}
            DynamicEmailSending(data).start()
            result['mensaje'] = 'Servicio activado con éxito.'
            result['correcto'] = True
            return result
        except:
            result['mensaje'] = 'Error en el mikrotik de Joven Club.'
            return result
    else:
        result['mensaje'] = 'No tiene suficientes coins.'
        return result

def comprar_emby(usuario):
    result = {'correcto': False}
    embyPrice = int(config('EMBY_PRICE'))
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result
    usuario = User.objects.get(username=usuario)
    profile = Profile.objects.get(usuario=usuario)
    servicio = EstadoServicio.objects.get(usuario=usuario.id)
    if servicio.emby == True:
        result['mensaje'] = 'Ya tiene el servicio activo.'
        return result
    if profile.coins >= embyPrice:
        profile.coins = profile.coins - embyPrice
        emby_ip = config('EMBY_IP')
        emby_api_key = config('EMBY_API_KEY')
        url = f'{ emby_ip }/Users/New?api_key={ emby_api_key }'
        json = {'Name': usuario.username}
        try:
            connect = requests.post(url=url, data=json)
            resp = connect.json()
            usuarioID = resp['Id']
            if connect.status_code == 200:
                profile.sync = False
                profile.save()
                servicio.emby = True
                servicio.emby_id = usuarioID
                servicio.emby_time = timezone.now() + timedelta(days=30)
                servicio.sync = False
                servicio.save()
                notificacion = Notificacion(usuario=usuario, tipo="PAGO", contenido="Emby activado")
                notificacion.save()
                url = f'{ emby_ip }/Users/{ usuarioID}/Configuration?api_key={ emby_api_key }'
                json = {
                            "PlayDefaultAudioTrack": True,
                            "DisplayMissingEpisodes": False,
                            "GroupedFolders": [],
                            "SubtitleMode": "Default",
                            "DisplayCollectionsView": False,
                            "EnableLocalPassword": False,
                            "OrderedViews": [],
                            "LatestItemsExcludes": [],
                            "MyMediaExcludes": [],
                            "HidePlayedInLatest": True,
                            "RememberAudioSelections": True,
                            "RememberSubtitleSelections": True,
                            "EnableNextEpisodeAutoPlay": True
                        }
                connect = requests.post(url=url, data=json)
                url = f'{ emby_ip }/Users/{ usuarioID}/Policy?api_key={ emby_api_key }'
                json = {
                            "IsAdministrator": False,
                            "IsHidden": True,
                            "IsHiddenRemotely": True,
                            "IsDisabled": False,
                            "BlockedTags": [],
                            "IsTagBlockingModeInclusive": False,
                            "EnableUserPreferenceAccess": True,
                            "AccessSchedules": [],
                            "BlockUnratedItems": [],
                            "EnableRemoteControlOfOtherUsers": False,
                            "EnableSharedDeviceControl": False,
                            "EnableRemoteAccess": False,
                            "EnableLiveTvManagement": False,
                            "EnableLiveTvAccess": False,
                            "EnableMediaPlayback": True,
                            "EnableAudioPlaybackTranscoding": True,
                            "EnableVideoPlaybackTranscoding": True,
                            "EnablePlaybackRemuxing": True,
                            "EnableContentDeletion": False,
                            "EnableContentDeletionFromFolders": [],
                            "EnableContentDownloading": False,
                            "EnableSubtitleDownloading": True,
                            "EnableSubtitleManagement": False,
                            "EnableSyncTranscoding": False,
                            "EnableMediaConversion": False,
                            "EnabledDevices": [],
                            "EnableAllDevices": True,
                            "EnabledChannels": [],
                            "EnableAllChannels": True,
                            "EnabledFolders": [],
                            "EnableAllFolders": True,
                            "InvalidLoginAttemptCount": 0,
                            "EnablePublicSharing": False,
                            "RemoteClientBitrateLimit": 0,
                            "AuthenticationProviderId": "Emby.Server.Implementations.Library.DefaultAuthenticationProvider",
                            "ExcludedSubFolders": [],
                            "SimultaneousStreamLimit": 1
                        }
                connect = requests.post(url=url, data=json)
                code = crearOper(usuario.username, "Emby", embyPrice)
                end_time = servicio.int_time.strftime('%B %d, a las %H:%M ')
                data = {'to': usuario.email, 'template_id': 'd-a9864607981c4305aedaf3d5277aa19b', 'dynamicdata': {'first_name': usuario.username, 'service': 'emby', 'end_time': end_time, 'code': code}}
                DynamicEmailSending(data).start()
                result['mensaje'] = 'Servicio activado con éxito.'
                result['correcto'] = True
                return result
            else:
                result['mensaje'] = 'Error en el servidor Emby.'
                return result
        except:
            result['mensaje'] = 'Ocurrió un error durante la activación del emby.'
            return result
    else:
        result['mensaje'] = 'No tiene suficientes coins.'
        return result

def comprar_filezilla(usuario, contraseña):
    result = {'correcto': False}
    ftpPrice = int(config('FTP_PRICE'))
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result
    usuario = User.objects.get(username=usuario)
    profile = Profile.objects.get(usuario=usuario)
    servicio = EstadoServicio.objects.get(usuario=usuario)
    if servicio.ftp == True:
        result['mensaje'] = 'Ya tiene el servicio activo.'
        return result
    if profile.coins >= ftpPrice:
        profile.coins = profile.coins - ftpPrice
        activarFTP(usuario, contraseña, group='usuarios')
        profile.sync = False
        profile.save()
        servicio.ftp = True
        servicio.ftp_time = timezone.now() + timedelta(days=30)
        code = crearOper(usuario.username, 'FileZilla', ftpPrice)
        end_time = servicio.ftp_time.strftime('%B %d, a las %H:%M ')
        data = {'to': usuario.email, 'template_id': 'd-a9864607981c4305aedaf3d5277aa19b', 'dynamicdata': {'first_name': usuario.username, 'service': 'filezilla', 'end_time': end_time, 'code': code}}
        DynamicEmailSending(data).start()
        servicio.sync = False
        servicio.save()
        notificacion = Notificacion(usuario=usuario, tipo="PAGO", contenido="Filezilla activado")
        notificacion.save()
        result['mensaje'] = 'Servicio activado con éxito.'
        result['correcto'] = True
        return result
    else:
        result['mensaje'] = 'No tiene suficientes coins.'
        return result

def recargar(code, usuario):
    result = {'correcto': False}
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result
    usuario = User.objects.get(username=usuario)
    profile = Profile.objects.get(usuario=usuario)
    if not profile.sync:
        result['mensaje'] = "Sincronice su perfil en dashboard para poder recargar."
        return result
    if len(code) != 8:
        result['mensaje'] = 'Escriba 8 dígitos.'
        return result
    if Recarga.objects.filter(code=code).exists():
        recarga = Recarga.objects.get(code=code)
        if recarga.activa:
            cantidad = recarga.cantidad       
            profile.coins = profile.coins + cantidad
            profile.sync = False
            profile.save()
            recarga.activa = False
            recarga.fechaUso = timezone.now()
            recarga.usuario = usuario
            recarga.sync = False
            recarga.save()
            contenido = f"Cuenta recargado con { cantidad } coins"
            notificacion = Notificacion(usuario=usuario, tipo="RECARGA", contenido=contenido)
            notificacion.save()
            oper = Oper(tipo='RECARGA', usuario=usuario, codRec=code, cantidad=cantidad)
            oper.save()
            result['correcto'] = True
            result['mensaje'] = 'Cuenta Recargada con éxito'
            return result
        else:
            result['mensaje'] = 'Esta recarga ya fue usada'
            return result
    else:
        data = {'usuario': usuario.username, 'code': code, 'check': True}
        respuesta = actualizacion_remota('usar_recarga', data=data)
        if respuesta['estado']:
            cantidad = respuesta['cantidad']            
            respuesta = actualizacion_remota('usar_recarga', {'usuario': usuario.username, 'code': code})
            if respuesta['estado']:
                profile.coins = profile.coins + cantidad
                profile.sync = False                      
                profile.save()
                contenido = f"Cuenta recargado con { cantidad } coins"
                notificacion = Notificacion(usuario=usuario, tipo="RECARGA", contenido=contenido)
                notificacion.save()
                oper = Oper(tipo='RECARGA', usuario=usuario, codRec=code, cantidad=cantidad)
                oper.save()
                result['correcto'] = True
        result['mensaje'] = respuesta['mensaje']
        return result

def transferir(desde, hacia, cantidad):
    result = {'correcto': False}
    conexion = EstadoConexion.objects.get(servidor=servidor)
    if not conexion.online:
        result['mensaje'] = "Sistema sin conexión, intente más tarde."
        return result    
    if User.objects.filter(username=hacia).exists():
        envia = User.objects.get(username=desde)
        enviaProfile = Profile.objects.get(usuario=envia)
        recibe = User.objects.get(username=hacia)
        recibeProfile = Profile.objects.get(usuario=recibe)
        if not enviaProfile.sync or not recibeProfile.sync:
            result['mensaje'] = "Sincronice ambos perfiles en dashboard para poder transferir"
            return result   
        coinsDesde = int(enviaProfile.coins) 
        cantidad = int(cantidad)
        if coinsDesde >= cantidad:
            if cantidad >= 20:                
                recibeProfile.coins = recibeProfile.coins + cantidad
                enviaProfile.coins = enviaProfile.coins - cantidad 
                enviaProfile.sync = False 
                enviaProfile.save()
                recibeProfile.sync = False
                recibeProfile.save()
                contenido = f"Usted transfirió { cantidad } coins a { recibe.username }"
                notificacion = Notificacion(usuario=envia, tipo="ENVIO", contenido=contenido)
                notificacion.save()
                oper = Oper(usuario=recibe, tipo="RECIBO", cantidad=cantidad, haciaDesde=desde)
                oper.save()  
                contenido = f"Usted recibió { cantidad } coins de { envia.username }"
                notificacion = Notificacion(usuario=recibe, tipo="RECIBO", contenido=contenido)
                notificacion.save() 
                oper2 = Oper(usuario=envia, tipo="ENVIO", cantidad=cantidad, haciaDesde=hacia)
                oper2.save()      
                result['mensaje']= 'Transferencia realizada con éxito'
                result['correcto'] = True
                return result
            else:
                result['mensaje'] = 'La cantidad mínima es 20'
                return result
        else:
            result['mensaje'] = 'Su cantidad es insuficiente'
            return result
    else:
        result['mensaje'] = 'El usuario de destino no existe'
        return result