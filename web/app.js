(function () {
  'use strict';

  var DATOS = window.RADAR_DATA;
  if (!DATOS) {
    document.body.innerHTML = '<p class="vacio">Falta <code>web/data.js</code>. Corre <code>python src/landing_data.py</code>.</p>';
    return;
  }

  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

  var dec1 = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var pct = new Intl.NumberFormat('es-AR', { style: 'percent', maximumFractionDigits: 0 });
  var SIN_TILDES = /[\u0300-\u036f]/g;

  function el(tag, clase, texto) {
    var nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined && texto !== null) nodo.textContent = texto;
    return nodo;
  }

  function sinAcentos(texto) {
    return String(texto || '').normalize('NFD').replace(SIN_TILDES, '').toLowerCase();
  }

  function fecha(iso) {
    return new Date(iso + 'T12:00:00Z');
  }

  function rango(iso) {
    var d = fecha(iso);
    return d.getUTCDate() + ' de ' + MESES[d.getUTCMonth()];
  }

  function rangoSemana(semana) {
    return rango(semana.inicio) + ' al ' + rango(semana.fin);
  }

  function pintarBug(semana) {
    document.querySelector('.bug__valor').textContent = semana.clave;
    document.querySelector('.bug__rango').textContent = rangoSemana(semana);
  }

  var semanas = DATOS.semanas;
  var actual = 0;

  function pintarSelector() {
    var caja = document.getElementById('selector-semana');
    caja.textContent = '';
    semanas.forEach(function (semana, i) {
      var boton = el('button', null, semana.clave.replace(/^\d{4}-/, ''));
      boton.type = 'button';
      boton.setAttribute('aria-label', 'Semana ' + semana.clave + ', ' + rangoSemana(semana));
      boton.setAttribute('aria-pressed', i === actual ? 'true' : 'false');
      boton.addEventListener('click', function () {
        actual = i;
        pintarSelector();
        pintarRadar();
      });
      caja.appendChild(boton);
    });
  }

  function itemCinta(termino, valor) {
    var div = el('div');
    div.appendChild(el('dt', null, termino));
    div.appendChild(el('dd', null, valor));
    return div;
  }

  function pintarRadar() {
    var semana = semanas[actual];
    pintarBug(semana);

    var caja = document.getElementById('planilla');
    caja.textContent = '';

    if (!semana.top.length) {
      caja.appendChild(el('p', 'vacio', 'Esa semana no tuvo candidatos: la liga estaba en parón o el equipo de la fecha todavía no estaba publicado.'));
    } else {
      var cabecera = el('div', 'planilla__cabecera');
      cabecera.appendChild(el('span'));
      cabecera.appendChild(el('span', null, 'Candidato'));
      cabecera.appendChild(el('span', null, 'Goles y asistencias'));
      caja.appendChild(cabecera);

      semana.top.forEach(function (j) {
        var fila = el('div', 'fila');
        fila.appendChild(el('span', 'fila__lugar', j.lugar));
        fila.appendChild(el('p', 'fila__nombre', j.nombre));

        var meta = el('p', 'fila__meta');
        meta.appendChild(el('span', null, j.club));
        meta.appendChild(el('span', null, j.liga));
        meta.appendChild(el('span', 'fila__puesto', j.puesto));
        if (j.edad) meta.appendChild(el('span', null, j.edad + ' años'));
        fila.appendChild(meta);

        var ga = el('p', 'fila__ga');
        ga.appendChild(document.createTextNode(j.goles + '+' + j.asistencias));
        ga.appendChild(el('small', null, j.partidos_temporada + ' partidos'));
        fila.appendChild(ga);

        caja.appendChild(fila);
      });
    }

    var cinta = document.getElementById('cinta');
    cinta.textContent = '';
    cinta.appendChild(itemCinta('Candidatos en el ranking', String(semana.jugadores)));
    cinta.appendChild(itemCinta('Ligas con equipo de la fecha', String(semana.ligas.length)));
    if (!semana.top.length) {
      cinta.appendChild(itemCinta('Semanas guardadas', String(semanas.length)));
    }
  }

/* ---------------- corte por puesto ---------------- */

  var GRUPOS = {
    DEL: 'delanteros y extremos',
    MED: 'mediocampistas',
    DEF: 'laterales y centrales'
  };

  function pintarPuesto(puesto) {
    var caja = el('div', 'puesto');
    var titulo = el('div', 'puesto__titulo');
    titulo.appendChild(el('b', null, puesto.macro));
    titulo.appendChild(el('span', null, GRUPOS[puesto.macro] || ''));
    caja.appendChild(titulo);

    puesto.jugadores.forEach(function (j, i) {
      var fila = el('div', 'puesto__fila');
      fila.appendChild(el('span', 'puesto__lugar', i + 1));

      var nombre = el('p', 'puesto__nombre');
      nombre.appendChild(document.createTextNode(j.nombre));
      nombre.appendChild(el('small', null, j.club));
      fila.appendChild(nombre);

      fila.appendChild(el('span', 'puesto__ga', j.goles + '+' + j.asistencias));

      var sent = el('span', 'puesto__sent');
      if (j.sentimiento === null) {
        sent.textContent = '\u2014';
      } else {
        if (j.sentimiento > 0) sent.classList.add('puesto__sent--pos');
        else if (j.sentimiento < 0) sent.classList.add('puesto__sent--neg');
        sent.textContent = (j.sentimiento > 0 ? '+' : '') + dec1.format(j.sentimiento);
      }
      fila.appendChild(sent);

      caja.appendChild(fila);
    });

    if (!puesto.jugadores.length) {
      caja.appendChild(el('p', 'puesto__vacio', 'Sin candidatos de este grupo esa semana.'));
    }
    return caja;
  }

  function pintarSemanaPuestos(semana) {
    var bloque = el('article', 'semana');
    var cabecera = el('div', 'semana__cabecera');
    cabecera.appendChild(el('h3', null, semana.clave));
    cabecera.appendChild(el('span', 'semana__rango', rangoSemana(semana)));
    cabecera.appendChild(el('span', 'semana__estado', semana.medidos
      ? semana.medidos + ' de ' + semana.seleccionados + ' con sentimiento'
      : 'sin sentimiento medido'));
    bloque.appendChild(cabecera);

    var puestos = el('div', 'semana__puestos');
    semana.puestos.forEach(function (puesto) {
      puestos.appendChild(pintarPuesto(puesto));
    });
    bloque.appendChild(puestos);
    return bloque;
  }

  function pintarPuestos() {
    var lista = document.getElementById('lista-puestos');
    semanas.forEach(function (semana) {
      lista.appendChild(pintarSemanaPuestos(semana));
    });
  }

  var ORDEN = {
    posicion: function (j) { return j.posicion; },
    nombre: function (j) { return sinAcentos(j.nombre); },
    liga: function (j) { return sinAcentos(j.liga); },
    apariciones_top5: function (j) { return j.apariciones_top5; },
    tasa_top5: function (j) { return j.tasa_top5; },
    mejor_posicion: function (j) { return j.mejor_posicion; },
    goles: function (j) { return (j.goles === null ? -1 : j.goles) + (j.asistencias || 0) / 100; },
    ultima_semana: function (j) { return j.ultima_semana; }
  };

  var columna = 'posicion';
  var sentido = 1;
  var textoBusqueda = '';
  var ligaElegida = '';
  var LIMITE = 25;
  var mostrarTodos = false;

  function guia(j) {
    var total = j.semanas_activas_liga;
    var llenas = Math.min(j.apariciones_top5, total);
    var medias = Math.max(0, Math.min(j.semanas_en_ranking - j.apariciones_top5, total - llenas));
    var caja = el('span', 'guia');
    caja.title = j.apariciones_top5 + ' de ' + j.semanas_en_ranking +
      ' semanas en el ranking, sobre ' + total + ' con equipo de la fecha en su liga';
    for (var i = 0; i < total; i++) {
      var clase = 'celda';
      if (i < llenas) clase += ' celda--llena';
      else if (i < llenas + medias) clase += ' celda--ranking';
      caja.appendChild(el('i', clase));
    }
    return caja;
  }

  function filaHistorico(j) {
    var tr = el('tr');
    tr.appendChild(el('td', null, j.posicion));

    var nombre = el('td');
    nombre.appendChild(document.createTextNode(j.nombre));
    nombre.appendChild(el('small', null, j.clubes));
    tr.appendChild(nombre);

    tr.appendChild(el('td', null, j.liga));

    var celdaGuia = el('td');
    celdaGuia.appendChild(guia(j));
    tr.appendChild(celdaGuia);

    tr.appendChild(el('td', null, j.apariciones_top5));
    tr.appendChild(el('td', null, pct.format(j.tasa_top5)));
    tr.appendChild(el('td', null, j.mejor_posicion));
    tr.appendChild(el('td', null, j.goles === null ? '—' : j.goles + '+' + j.asistencias));
    tr.appendChild(el('td', null, j.ultima_semana));
    return tr;
  }

  function pintarHistorico() {
    var lista = DATOS.historico.filter(function (j) {
      if (ligaElegida && j.liga !== ligaElegida) return false;
      if (!textoBusqueda) return true;
      return sinAcentos(j.nombre + ' ' + j.clubes).indexOf(textoBusqueda) >= 0;
    });

    lista = lista.slice().sort(function (a, b) {
      var va = ORDEN[columna](a);
      var vb = ORDEN[columna](b);
      if (va < vb) return -sentido;
      if (va > vb) return sentido;
      return a.posicion - b.posicion;
    });

    var cuerpo = document.getElementById('cuerpo-tabla');
    cuerpo.textContent = '';
    lista.slice(0, mostrarTodos ? lista.length : LIMITE)
      .forEach(function (j) { cuerpo.appendChild(filaHistorico(j)); });

    var boton = document.getElementById('ver-todos');
    boton.hidden = lista.length <= LIMITE || mostrarTodos;
    boton.textContent = 'Mostrar los ' + lista.length + ' jugadores';
    boton.onclick = function () {
      mostrarTodos = true;
      pintarHistorico();
    };

    document.getElementById('conteo').textContent = lista.length === DATOS.historico.length
      ? DATOS.historico.length + ' jugadores en ' + DATOS.semanas.length + ' semanas'
      : lista.length + ' de ' + DATOS.historico.length + ' jugadores';
  }

  function conectarOrden() {
    var ths = document.querySelectorAll('.tabla thead th[data-orden]');
    Array.prototype.forEach.call(ths, function (th) {
      var boton = th.querySelector('button');
      if (!boton || !ORDEN[th.dataset.orden]) return;
      boton.addEventListener('click', function () {
        var campo = th.dataset.orden;
        sentido = columna === campo ? -sentido : (campo === 'nombre' || campo === 'liga' ? 1 : -1);
        columna = campo;
        Array.prototype.forEach.call(ths, function (otro) { otro.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', sentido === 1 ? 'ascending' : 'descending');
        pintarHistorico();
      });
    });
    var primero = document.querySelector('.tabla thead th[data-orden="posicion"]');
    if (primero) primero.setAttribute('aria-sort', 'ascending');
  }

  function conectarFiltros() {
    var ligas = [];
    DATOS.historico.forEach(function (j) { if (ligas.indexOf(j.liga) < 0) ligas.push(j.liga); });
    ligas.sort();
    var select = document.getElementById('filtro-liga');
    ligas.forEach(function (liga) {
      var opcion = el('option', null, liga);
      opcion.value = liga;
      select.appendChild(opcion);
    });
    select.addEventListener('change', function () {
      ligaElegida = select.value;
      mostrarTodos = false;
      pintarHistorico();
    });
    var buscar = document.getElementById('buscar');
    buscar.addEventListener('input', function () {
      textoBusqueda = sinAcentos(buscar.value.trim());
      mostrarTodos = false;
      pintarHistorico();
    });
  }

  function pintarFeatures() {
    var lista = document.getElementById('features');
    DATOS.modelo.features.forEach(function (f) {
      var esPos = f.indexOf('pos_') === 0;
      var item = el('li', null, esPos ? f.slice(4).replace(/_/g, ' ').toLowerCase() : f);
      if (esPos) item.setAttribute('data-tipo', 'posicion');
      lista.appendChild(item);
    });
  }

  document.getElementById('generado').textContent = fecha(DATOS.generado).toLocaleDateString('es-AR', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'
  });

  pintarSelector();
  pintarRadar();
  pintarPuestos();
  conectarOrden();
  conectarFiltros();
  pintarHistorico();
  pintarFeatures();
})();