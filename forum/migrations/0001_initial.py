# Generated by Django 5.0.1 on 2024-02-06 02:55

import django.db.models.deletion
import django.utils.timezone
import forum.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Publicacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tema', models.CharField(choices=[('Noticia', 'Noticia'), ('Internet', 'Internet'), ('JovenClub', 'JovenClub'), ('Emby', 'Emby'), ('FileZilla', 'FileZilla'), ('QbaRed', 'QbaRed')], max_length=15)),
                ('titulo', models.CharField(max_length=60, unique=True)),
                ('slug', models.SlugField(max_length=60)),
                ('contenido', models.TextField()),
                ('fecha', models.DateTimeField(default=django.utils.timezone.now)),
                ('sync', models.BooleanField(default=False)),
                ('visitas', models.PositiveIntegerField(default=0)),
                ('imagen1', models.ImageField(default='defaultForum.png', upload_to=forum.models.upload_to, verbose_name='Imagen1')),
                ('imagen2', models.ImageField(default='defaultForum.png', upload_to=forum.models.upload_to, verbose_name='Imagen2')),
                ('imagen3', models.ImageField(default='defaultForum.png', upload_to=forum.models.upload_to, verbose_name='Imagen3')),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Encuesta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('opcion1', models.CharField(max_length=60)),
                ('opcion2', models.CharField(max_length=60)),
                ('opcion3', models.CharField(max_length=60)),
                ('opcion4', models.CharField(max_length=60)),
                ('opcion5', models.CharField(max_length=60)),
                ('voto1', models.ManyToManyField(related_name='Opcion1', to=settings.AUTH_USER_MODEL)),
                ('voto2', models.ManyToManyField(related_name='Opcion2', to=settings.AUTH_USER_MODEL)),
                ('voto3', models.ManyToManyField(related_name='Opcion3', to=settings.AUTH_USER_MODEL)),
                ('voto4', models.ManyToManyField(related_name='Opcion4', to=settings.AUTH_USER_MODEL)),
                ('voto5', models.ManyToManyField(related_name='Opcion5', to=settings.AUTH_USER_MODEL)),
                ('publicacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='forum.publicacion')),
            ],
        ),
        migrations.CreateModel(
            name='Comentario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(default=django.utils.timezone.now)),
                ('contenido', models.TextField()),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('publicacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='forum.publicacion')),
            ],
        ),
        migrations.CreateModel(
            name='RespuestaComentario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(default=django.utils.timezone.now)),
                ('contenido', models.TextField()),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('comentario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='forum.publicacion')),
            ],
        ),
    ]
