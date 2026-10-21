/*
 * Lanzador de los fPKG de Dreamcast y GameCube/Wii de ps2-fpkg (eboot.bin del paquete).
 *
 * Dreamcast: el paquete trae Resonance (Flycast para PS4, GPL-2.0) en /app0/resonance/eboot.bin.
 * Se lee /app0/autoboot/args.txt (un argumento por línea: opciones "-config sección:clave=valor"
 * y al final la ruta del juego) y se arranca Resonance con ellos; Flycast inicia ese juego
 * directamente y al cerrarlo se sale de la app.
 *
 * GameCube/Wii: el paquete trae DolphinPS4 (GPL-2.0) en /app0/dolphin/eboot.bin, que no lee
 * argumentos: arranca el juego que nombra /data/DolphinPS4/launch.txt. Se escribe ahí la ruta de
 * /app0/autoboot/dolphin.txt y se arranca Dolphin. Al salir del juego, Dolphin deja
 * /data/DolphinPS4/to-menu.txt y vuelve a abrir /app0/eboot.bin (este programa): entonces se
 * cierra la app en lugar de mostrar el menú de Dolphin. Con "Reiniciar juego", Dolphin ya dejó
 * launch.txt escrito y solo hay que volver a arrancarlo.
 */
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include <orbis/SystemService.h>

#define ARGS_FILE "/app0/autoboot/args.txt"
#define RESONANCE "/app0/resonance/eboot.bin"
#define DOLPHIN_FILE "/app0/autoboot/dolphin.txt"
#define DOLPHIN "/app0/dolphin/eboot.bin"
#define DOLPHIN_DATA "/data/DolphinPS4"
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

static int fail(const char *what, int code)
{
	char msg[200];
	snprintf(msg, sizeof(msg), "%s (0x%08x)", what, (unsigned)code);
	notify(msg);
	sleep(5);
	return 1;
}

static size_t read_text(const char *path, char *text, size_t size)
{
	FILE *f = fopen(path, "r");
	if (f == NULL)
		return 0;
	size_t len = fread(text, 1, size - 1, f);
	fclose(f);
	text[len] = '\0';
	return len;
}

/* Divide el texto en líneas no vacías (sin \r ni espacios finales). */
static int split_lines(char *text, const char **lines, int max)
{
	int n = 0;
	char *line = text;
	while (*line != '\0' && n < max)
	{
		char *next = strchr(line, '\n');
		if (next != NULL)
			*next = '\0';
		size_t l = strlen(line);
		while (l > 0 && (line[l - 1] == '\r' || line[l - 1] == ' '))
			line[--l] = '\0';
		if (l > 0)
			lines[n++] = line;
		if (next == NULL)
			break;
		line = next + 1;
	}
	lines[n] = NULL;
	return n;
}

static int run_resonance(void)
{
	static char text[8192];
	static const char *args[MAX_ARGS + 1];
	read_text(ARGS_FILE, text, sizeof(text));
	split_lines(text, args, MAX_ARGS);
	return fail("No se pudo iniciar Resonance", sceSystemServiceLoadExec(RESONANCE, args));
}

/* Un archivo de /data/DolphinPS4 recién escrito (hace menos de 2 minutos): uno viejo es de
 * otra sesión (la app Dolphin) y no cuenta. */
static int recent(const char *path)
{
	struct stat st;
	if (stat(path, &st) != 0)
		return 0;
	return time(NULL) - st.st_mtime < 120;
}

static int run_dolphin(void)
{
	static char text[1024];
	const char *lines[2];
	const char *to_menu = DOLPHIN_DATA "/to-menu.txt";
	const char *launch = DOLPHIN_DATA "/launch.txt";

	if (access(to_menu, F_OK) == 0)
	{
		int quit = recent(to_menu);
		remove(to_menu);
		if (quit)
		{
			// Se salió del juego: se cierra la app.
			sceSystemServiceLoadExec("exit", NULL);
			for (;;)
				sleep(1);
		}
	}
	if (!recent(launch))
	{
		read_text(DOLPHIN_FILE, text, sizeof(text));
		if (split_lines(text, lines, 1) == 0)
			return fail("Falta " DOLPHIN_FILE, 0);
		mkdir(DOLPHIN_DATA, 0777);
		mkdir(DOLPHIN_DATA "/games", 0777);
		FILE *f = fopen(launch, "w");
		if (f == NULL)
			return fail("No se pudo escribir " DOLPHIN_DATA "/launch.txt", 0);
		fprintf(f, "%s\n", lines[0]);
		fclose(f);
	}
	return fail("No se pudo iniciar Dolphin", sceSystemServiceLoadExec(DOLPHIN, NULL));
}

int main(void)
{
	if (access(DOLPHIN_FILE, F_OK) == 0)
		return run_dolphin();
	if (access(ARGS_FILE, F_OK) == 0)
		return run_resonance();
	return fail("Falta " ARGS_FILE, 0);
}
