/*
 * Lanzador de los fPKG de Dreamcast de ps2-fpkg.
 *
 * El paquete trae Resonance (Flycast para PS4, GPL-2.0) en /app0/resonance/eboot.bin y el juego
 * en /app0/autoboot/. Este programa lee /app0/autoboot/args.txt (un argumento por línea: las
 * opciones "-config sección:clave=valor" y al final la ruta del juego) y arranca Resonance con
 * ellos; Flycast inicia ese juego directamente y al cerrarlo se sale de la app.
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include <orbis/SystemService.h>

#define ARGS_FILE "/app0/autoboot/args.txt"
#define EMULATOR "/app0/resonance/eboot.bin"
#define MAX_ARGS 32

static void notify(const char *text)
{
	OrbisNotificationRequest req;
	memset(&req, 0, sizeof(req));
	req.type = NotificationRequest;
	req.targetId = -1;
	strncpy(req.message, text, sizeof(req.message) - 1);
	sceKernelSendNotificationRequest(0, &req, sizeof(req), 0);
}

int main(void)
{
	static char text[8192];
	static const char *args[MAX_ARGS + 1];
	int n = 0;

	FILE *f = fopen(ARGS_FILE, "r");
	if (f == NULL)
	{
		notify("Falta " ARGS_FILE);
		sleep(5);
		return 1;
	}
	size_t len = fread(text, 1, sizeof(text) - 1, f);
	fclose(f);
	text[len] = '\0';

	char *line = text;
	while (*line != '\0' && n < MAX_ARGS)
	{
		char *next = strchr(line, '\n');
		if (next != NULL)
			*next = '\0';
		size_t l = strlen(line);
		while (l > 0 && (line[l - 1] == '\r' || line[l - 1] == ' '))
			line[--l] = '\0';
		if (l > 0)
			args[n++] = line;
		if (next == NULL)
			break;
		line = next + 1;
	}
	args[n] = NULL;

	int r = sceSystemServiceLoadExec(EMULATOR, args);
	// solo vuelve si no se pudo arrancar
	char msg[160];
	snprintf(msg, sizeof(msg), "No se pudo iniciar Resonance (error 0x%08x)", (unsigned)r);
	notify(msg);
	sleep(5);
	return 1;
}
