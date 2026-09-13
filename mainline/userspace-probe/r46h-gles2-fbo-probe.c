#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>

#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PROBE_WIDTH 64
#define PROBE_HEIGHT 64

static void fail(const char *message)
{
	fprintf(stderr, "R46H_MESA_PROBE result=fail reason=%s egl=0x%04x gl=0x%04x\n",
		message, eglGetError(), glGetError());
	exit(EXIT_FAILURE);
}

static bool contains_case_insensitive(const char *haystack, const char *needle)
{
	size_t needle_len;

	if (!haystack || !needle)
		return false;

	needle_len = strlen(needle);
	if (!needle_len)
		return true;

	for (; *haystack; haystack++) {
		size_t i;

		for (i = 0; i < needle_len; i++) {
			if (!haystack[i] ||
			    tolower((unsigned char)haystack[i]) !=
			    tolower((unsigned char)needle[i]))
				break;
		}
		if (i == needle_len)
			return true;
	}

	return false;
}

static GLuint compile_shader(GLenum type, const char *source)
{
	GLuint shader = glCreateShader(type);
	GLint status = GL_FALSE;
	GLint log_len = 0;

	if (!shader)
		fail("create-shader");

	glShaderSource(shader, 1, &source, NULL);
	glCompileShader(shader);
	glGetShaderiv(shader, GL_COMPILE_STATUS, &status);
	if (status == GL_TRUE)
		return shader;

	glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &log_len);
	if (log_len > 1) {
		char *log = calloc((size_t)log_len, 1);

		if (log) {
			glGetShaderInfoLog(shader, log_len, NULL, log);
			fprintf(stderr, "shader-log: %s\n", log);
			free(log);
		}
	}
	fail("compile-shader");
	return 0;
}

static GLuint link_program(GLuint vertex_shader, GLuint fragment_shader)
{
	GLuint program = glCreateProgram();
	GLint status = GL_FALSE;
	GLint log_len = 0;

	if (!program)
		fail("create-program");

	glAttachShader(program, vertex_shader);
	glAttachShader(program, fragment_shader);
	glBindAttribLocation(program, 0, "a_position");
	glLinkProgram(program);
	glGetProgramiv(program, GL_LINK_STATUS, &status);
	if (status == GL_TRUE)
		return program;

	glGetProgramiv(program, GL_INFO_LOG_LENGTH, &log_len);
	if (log_len > 1) {
		char *log = calloc((size_t)log_len, 1);

		if (log) {
			glGetProgramInfoLog(program, log_len, NULL, log);
			fprintf(stderr, "program-log: %s\n", log);
			free(log);
		}
	}
	fail("link-program");
	return 0;
}

int main(void)
{
	static const EGLint config_attributes[] = {
		EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
		EGL_RED_SIZE, 8,
		EGL_GREEN_SIZE, 8,
		EGL_BLUE_SIZE, 8,
		EGL_ALPHA_SIZE, 8,
		EGL_NONE,
	};
	static const EGLint pbuffer_attributes[] = {
		EGL_WIDTH, PROBE_WIDTH,
		EGL_HEIGHT, PROBE_HEIGHT,
		EGL_NONE,
	};
	static const EGLint context_attributes[] = {
		EGL_CONTEXT_CLIENT_VERSION, 2,
		EGL_NONE,
	};
	static const char vertex_source[] =
		"attribute vec2 a_position;\n"
		"void main(void) {\n"
		"  gl_Position = vec4(a_position, 0.0, 1.0);\n"
		"}\n";
	static const char fragment_source[] =
		"precision mediump float;\n"
		"void main(void) {\n"
		"  gl_FragColor = vec4(0.2, 0.4, 0.6, 1.0);\n"
		"}\n";
	static const GLfloat vertices[] = {
		-1.0f, -1.0f,
		 3.0f, -1.0f,
		-1.0f,  3.0f,
	};
	PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform_display;
	EGLDisplay display = EGL_NO_DISPLAY;
	EGLConfig config = NULL;
	EGLint config_count = 0;
	EGLint major = 0;
	EGLint minor = 0;
	EGLSurface surface = EGL_NO_SURFACE;
	EGLContext context = EGL_NO_CONTEXT;
	const char *vendor;
	const char *renderer;
	const char *version;
	GLuint vertex_shader;
	GLuint fragment_shader;
	GLuint program;
	GLuint texture = 0;
	GLuint framebuffer = 0;
	uint8_t pixel[4] = { 0, 0, 0, 0 };
	int channel;
	static const int expected[4] = { 51, 102, 153, 255 };

	get_platform_display = (PFNEGLGETPLATFORMDISPLAYEXTPROC)
		eglGetProcAddress("eglGetPlatformDisplayEXT");
	if (get_platform_display)
		display = get_platform_display(EGL_PLATFORM_SURFACELESS_MESA,
			EGL_DEFAULT_DISPLAY, NULL);
	if (display == EGL_NO_DISPLAY)
		display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	if (display == EGL_NO_DISPLAY)
		fail("get-display");

	if (eglInitialize(display, &major, &minor) != EGL_TRUE)
		fail("initialize-egl");
	if (eglBindAPI(EGL_OPENGL_ES_API) != EGL_TRUE)
		fail("bind-gles-api");
	if (eglChooseConfig(display, config_attributes, &config, 1,
			    &config_count) != EGL_TRUE || config_count != 1)
		fail("choose-config");

	surface = eglCreatePbufferSurface(display, config, pbuffer_attributes);
	if (surface == EGL_NO_SURFACE)
		fail("create-pbuffer");
	context = eglCreateContext(display, config, EGL_NO_CONTEXT,
				   context_attributes);
	if (context == EGL_NO_CONTEXT)
		fail("create-context");
	if (eglMakeCurrent(display, surface, surface, context) != EGL_TRUE)
		fail("make-current");

	vendor = (const char *)glGetString(GL_VENDOR);
	renderer = (const char *)glGetString(GL_RENDERER);
	version = (const char *)glGetString(GL_VERSION);
	printf("R46H_MESA_PROBE egl=%d.%d vendor=%s renderer=%s version=%s\n",
		major, minor, vendor ? vendor : "(null)",
		renderer ? renderer : "(null)", version ? version : "(null)");
	if (!contains_case_insensitive(vendor, "mesa"))
		fail("non-mesa-vendor");
	if (!contains_case_insensitive(renderer, "panfrost") &&
	    !contains_case_insensitive(renderer, "mali-g31"))
		fail("non-panfrost-renderer");
	if (contains_case_insensitive(renderer, "llvmpipe") ||
	    contains_case_insensitive(renderer, "softpipe") ||
	    contains_case_insensitive(renderer, "swrast"))
		fail("software-renderer");

	vertex_shader = compile_shader(GL_VERTEX_SHADER, vertex_source);
	fragment_shader = compile_shader(GL_FRAGMENT_SHADER, fragment_source);
	program = link_program(vertex_shader, fragment_shader);

	glGenTextures(1, &texture);
	glBindTexture(GL_TEXTURE_2D, texture);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, PROBE_WIDTH, PROBE_HEIGHT, 0,
		     GL_RGBA, GL_UNSIGNED_BYTE, NULL);
	glGenFramebuffers(1, &framebuffer);
	glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
			       GL_TEXTURE_2D, texture, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
		fail("incomplete-framebuffer");

	glViewport(0, 0, PROBE_WIDTH, PROBE_HEIGHT);
	glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	glUseProgram(program);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, vertices);
	glEnableVertexAttribArray(0);
	glDrawArrays(GL_TRIANGLES, 0, 3);
	glFinish();
	glReadPixels(PROBE_WIDTH / 2, PROBE_HEIGHT / 2, 1, 1,
		     GL_RGBA, GL_UNSIGNED_BYTE, pixel);
	if (glGetError() != GL_NO_ERROR)
		fail("render-or-readback");

	for (channel = 0; channel < 4; channel++) {
		int delta = (int)pixel[channel] - expected[channel];

		if (delta < -1 || delta > 1)
			fail("pixel-mismatch");
	}

	printf("R46H_MESA_PROBE pixel=%u,%u,%u,%u expected=51,102,153,255\n",
		pixel[0], pixel[1], pixel[2], pixel[3]);
	printf("R46H_MESA_PROBE result=pass\n");

	glDeleteFramebuffers(1, &framebuffer);
	glDeleteTextures(1, &texture);
	glDeleteProgram(program);
	glDeleteShader(fragment_shader);
	glDeleteShader(vertex_shader);
	eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
	eglDestroyContext(display, context);
	eglDestroySurface(display, surface);
	eglTerminate(display);

	return EXIT_SUCCESS;
}
