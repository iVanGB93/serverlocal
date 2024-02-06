from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from decouple import config
from .models import Profile
from servicios.models import EstadoServicio
from sync.syncs import actualizacion_remota
from sync.models import EstadoConexion
from sync.actions import UpdateThreadUsuario


def entrar(request):
    if request.user.is_authenticated:
        return redirect ('web:index')
    if request.method == 'POST':
        content = {'icon': 'error'}
        username = request.POST['username']
        password = request.POST['password']
        if User.objects.filter(username=username).exists():
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('web:index')
            else:
                content['mensaje'] = "Contraseña Incorrecta"
                return render(request, 'users/login.html', content)            
        else:
            check_user = actualizacion_remota('check_usuario', {'usuario': username})
            if not check_user['conexion']:
                content['mensaje'] = "Servidor sin conexion, intente mas tarde."
                return render(request, 'users/login.html', content)
            if check_user['estado']:
                content['mensaje'] = "Su usuario no se encuentra en la local."
                send_username = username
                return redirect('users:pullUser', user=send_username)
            else:
                content['mensaje'] = "Usuario no existe"
                return render(request, 'users/login.html', content)
    else:
        return render(request, 'users/login.html')

def register(request):
    if request.user.is_authenticated:
        return redirect ('web:index')
    content = {'icon': 'error'}
    if request.method == 'POST':
        online = config('APP_MODE')
        if online == 'online':
            conexion = EstadoConexion.objects.get(id=1)
            if not conexion.online:
                content['mensaje'] = "Registro deshabilitado, intente más tarde."
                return render(request, 'users/register.html', content)
        password = request.POST['password']
        if len(password) <8:
            content['mensaje'] = "Contraseña mínimo 8 caracteres."
            return render(request, 'users/register.html', content)
        password2 = request.POST['passwordConfirm']
        if password != password2:
            content['mensaje'] = "Las contraseñas no coinciden."
            return render(request, 'users/register.html', content)
        email = request.POST['email']
        username = request.POST['username']
        if User.objects.filter(username=username).exists():
            content['mensaje'] = "Nombre de usuario en uso."
            return render(request, 'users/register.html', content)
        if User.objects.filter(email=email).exists():
            content['mensaje'] = "Correo en uso."
            return render(request, 'users/register.html', content)
        if online == 'online':
            check_user = actualizacion_remota('check_usuario', {'usuario': username})
            if check_user['conexion']:
                if check_user['estado']:
                    content['mensaje'] = check_user['mensaje']
                    return render(request, 'users/register.html', content)
            else:
                content['mensaje'] = "Registro deshabilitado, intente más tarde."
                return render(request, 'users/register.html', content)
            check_email = actualizacion_remota('check_email', {'email': email})
            if check_email['conexion']:
                if check_email['estado']:
                    content['mensaje'] = check_email['mensaje']
                    return render(request, 'users/register.html', content)
            else:
                content['mensaje'] = "Registro deshabilitado, intente más tarde."
                return render(request, 'users/register.html', content)
        user = User(username=username, email=email)
        user.set_password(password)
        user.save()
        new_user = authenticate(request, username=user.username, password=password)        
        UpdateThreadUsuario({'usuario':user.username, 'email': user.email, 'password': password}).start()
        login(request, new_user)
        return redirect('web:index')                  
    else:        
        return render(request, 'users/register.html')
    
def salir(request):
    logout(request)
    return redirect('web:index')

def pullUser(request, user):
    content = {'icon': 'error', 'user': user}
    if request.method == 'POST':
        password = request.POST['password']
        information = actualizacion_remota('get_user_info', {'usuario': user, 'password': password})
        if not information['estado']:
            content['mensaje'] = information['mensaje']
            return render(request, 'users/pullUser.html', content)
        new_user = User(username=information['username'], email=information['email'])
        new_user.set_password(password)
        new_user.save()
        profile = Profile.objects.get(usuario=new_user)
        profile.coins = information['coins']
        profile.sync - True
        profile.save()
        services = EstadoServicio.objects.get(usuario=new_user)
        services.internet  = information['internet']                               
        services.int_horas = information['int_horas']
        if information['int_time'] != 'None':
            services.int_time = information['int_time']
        services.int_tipo = information['int_tipo']
        services.int_duracion = information['int_duracion']
        services.int_velocidad = information['int_velocidad']
        services.int_auto = information['int_auto']
        services.jc = information['jc']
        if information['jc_time'] != 'None':
            services.jc_time = information['jc_time']
        services.jc_auto = information['jc_auto']
        services.emby = information['emby']
        services.emby_id = information['emby_id']
        if information['emby_time'] != 'None':
            services.emby_time = information['emby_time']
        services.emby_auto = information['emby_auto']
        services.ftp = information['ftp']
        services.ftp_auto = information['ftp_auto']
        if information['ftp_time'] != 'None':
            services.ftp_time = information['ftp_time']
        services.sync = True
        services.save()
        content['icon'] = 'success'
        content['mensaje'] = "Ya puede entrar con su usuario"
        return render(request, 'users/login.html', content)
    return render(request, 'users/pullUser.html', content)