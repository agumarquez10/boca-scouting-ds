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

  var NOMBRES_FEATURES = {
    goles: 'Goles de la temporada',
    asistencias: 'Asistencias de la temporada',
    edad: 'Edad',
    pos_Defensor_central: 'Posición: defensor central',
    pos_Delantero: 'Posición: delantero',
    pos_Extremo: 'Posición: extremo',
    pos_Lateral: 'Posición: lateral',
    pos_Mediocampista_central: 'Posición: mediocampista central',
    pos_Mediocampista_ofensivo: 'Posición: mediocampista ofensivo'
  };

  function el(tag, clase, texto) {
    var nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined && texto !== null) nodo.textContent = texto;
    return nodo;
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
      caja.appendChild(el('p', 'vacio', 'No hay candidatos guardados para esta semana. Puede que FotMob todavía no haya publicado el equipo de la fecha o que no hubiera datos suficientes para puntuarlo.'));
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
    DEF: 'laterales y centrales',
    SENT: 'tono de las menciones en YouTube y prensa'
  };

  function filaPuesto(j, lugar) {
    var fila = el('div', 'puesto__fila');
    if (!j) fila.classList.add('puesto__fila--vacia');
    fila.appendChild(el('span', 'puesto__lugar', lugar));

    var nombre = el('p', 'puesto__nombre');
    nombre.appendChild(document.createTextNode(j ? j.nombre : 'sin medición'));
    if (j) nombre.appendChild(el('small', null, j.club));
    fila.appendChild(nombre);

    fila.appendChild(el('span', 'puesto__ga', j ? j.goles + '+' + j.asistencias : ''));

    var sent = el('span', 'puesto__sent');
    if (!j || j.sentimiento === null || j.sentimiento === undefined) {
      sent.textContent = '—';
    } else {
      if (j.sentimiento > 0) sent.classList.add('puesto__sent--pos');
      else if (j.sentimiento < 0) sent.classList.add('puesto__sent--neg');
      sent.textContent = (j.sentimiento > 0 ? '+' : '') + dec1.format(j.sentimiento);
      var partes = [];
      if (j.prensa !== null && j.prensa !== undefined) {
        var textoPrensa = 'Prensa ' + dec1.format(j.prensa);
        if (j.prensa_n_textos !== null && j.prensa_n_textos !== undefined) {
          textoPrensa += ' (' + j.prensa_n_textos + ' textos RSS)';
        }
        partes.push(textoPrensa);
      }
      if (j.youtube !== null && j.youtube !== undefined) {
        var textoYouTube = 'YouTube ' + dec1.format(j.youtube);
        if (j.youtube_n_comentarios !== null && j.youtube_n_comentarios !== undefined) {
          textoYouTube += ' (' + j.youtube_n_comentarios + ' comentarios)';
        }
        partes.push(textoYouTube);
      }
      sent.title = partes.join(' · ') + ' · ' + j.n_fuentes + (j.n_fuentes === 1 ? ' fuente' : ' fuentes');
    }
    fila.appendChild(sent);
    return fila;
  }

  function pintarPuesto(puesto, ancho) {
    var caja = el('div', 'puesto');
    if (ancho) caja.classList.add('puesto--ancho');

    var titulo = el('div', 'puesto__titulo');
    titulo.appendChild(el('b', null, puesto.macro));
    titulo.appendChild(el('span', null, GRUPOS[puesto.macro] || ''));
    caja.appendChild(titulo);

    var lista = puesto.jugadores || [];
    var cups = ancho ? 3 : lista.length;
    for (var i = 0; i < cups; i++) {
      caja.appendChild(filaPuesto(lista[i] || null, i + 1));
    }
    if (!cups) {
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
      ? semana.medidos + ' de ' + semana.seleccionados + ' con medición'
      : 'sin mediciones guardadas'));
    bloque.appendChild(cabecera);

    var puestos = el('div', 'semana__puestos');
    semana.puestos.forEach(function (puesto) {
      puestos.appendChild(pintarPuesto(puesto, false));
    });
    puestos.appendChild(pintarPuesto({
      macro: 'SENT',
      jugadores: semana.sentimiento
    }, true));
    bloque.appendChild(puestos);
    return bloque;
  }

  function pintarPuestos() {
    var lista = document.getElementById('lista-puestos');
    semanas.forEach(function (semana) {
      lista.appendChild(pintarSemanaPuestos(semana));
    });
  }

  var FORMATO_PORCENTAJE = new Intl.NumberFormat('es-AR', {
    style: 'percent', maximumFractionDigits: 0
  });
  var SIN_TILDES = /[\u0300-\u036f]/g;
  var LIMITE_HISTORICO = 25;
  var historicoColumna = 'posicion';
  var historicoSentido = 1;
  var historicoBusqueda = '';
  var historicoLiga = '';
  var historicoMostrarTodos = false;

  var ORDEN_HISTORICO = {
    posicion: function (j) { return j.posicion; },
    nombre: function (j) { return sinAcentos(j.nombre); },
    liga: function (j) { return sinAcentos(j.liga); },
    apariciones_top5: function (j) { return j.apariciones_top5; },
    tasa_top5: function (j) { return j.tasa_top5; },
    mejor_posicion: function (j) { return j.mejor_posicion; },
    ultima_semana: function (j) { return j.ultima_semana; }
  };

  function sinAcentos(texto) {
    return String(texto || '').normalize('NFD').replace(SIN_TILDES, '').toLowerCase();
  }

  function filaHistorico(j) {
    var tr = el('tr');
    tr.appendChild(el('td', null, j.posicion));

    var nombre = el('td');
    nombre.appendChild(document.createTextNode(j.nombre));
    if (j.clubes) nombre.appendChild(el('small', null, j.clubes));
    tr.appendChild(nombre);

    tr.appendChild(el('td', null, j.liga));
    tr.appendChild(el('td', null, j.apariciones_top5));

    var tasa = el('td', null, FORMATO_PORCENTAJE.format(j.tasa_top5));
    tasa.title = j.apariciones_top5 + ' apariciones entre ' + j.semanas_activas_liga +
      ' semanas con datos para la liga';
    tr.appendChild(tasa);

    tr.appendChild(el('td', null, j.mejor_posicion));
    tr.appendChild(el('td', null, j.ultima_semana));
    return tr;
  }

  function pintarHistorico() {
    var todos = DATOS.historico || [];
    var lista = todos.filter(function (j) {
      if (historicoLiga && j.liga !== historicoLiga) return false;
      if (!historicoBusqueda) return true;
      return sinAcentos(j.nombre + ' ' + (j.clubes || '')).indexOf(historicoBusqueda) >= 0;
    });

    var obtener = ORDEN_HISTORICO[historicoColumna];
    lista.sort(function (a, b) {
      var va = obtener(a);
      var vb = obtener(b);
      if (typeof va === 'string') va = sinAcentos(va);
      if (typeof vb === 'string') vb = sinAcentos(vb);
      if (va < vb) return -historicoSentido;
      if (va > vb) return historicoSentido;
      return a.posicion - b.posicion;
    });

    var visibles = historicoMostrarTodos
      ? lista.length : Math.min(lista.length, LIMITE_HISTORICO);
    var cuerpo = document.getElementById('cuerpo-historico');
    cuerpo.textContent = '';
    if (!lista.length) {
      var vacio = el('tr');
      var celdaVacia = el('td', 'historico__vacio', 'No hay jugadores que coincidan con esos filtros.');
      celdaVacia.colSpan = 7;
      vacio.appendChild(celdaVacia);
      cuerpo.appendChild(vacio);
    } else {
      lista.slice(0, visibles).forEach(function (j) {
        cuerpo.appendChild(filaHistorico(j));
      });
    }

    var conteo = document.getElementById('conteo-historico');
    conteo.textContent = 'Mostrando ' + visibles + ' de ' + lista.length + ' jugadores' +
      (lista.length === todos.length ? '' : ' (' + todos.length + ' en total)');

    var boton = document.getElementById('mostrar-historico');
    boton.hidden = lista.length <= LIMITE_HISTORICO;
    boton.textContent = historicoMostrarTodos ? 'Mostrar menos' : 'Mostrar los ' + lista.length + ' jugadores';
    actualizarOrdenHistorico();
  }

  function actualizarOrdenHistorico() {
    var ths = document.querySelectorAll('#tabla-historico thead th[data-orden]');
    Array.prototype.forEach.call(ths, function (th) {
      th.removeAttribute('aria-sort');
      if (th.dataset.orden === historicoColumna) {
        th.setAttribute('aria-sort', historicoSentido === 1 ? 'ascending' : 'descending');
      }
    });
  }

  function conectarHistorico() {
    var datos = DATOS.historico || [];
    var ligas = [];
    datos.forEach(function (j) {
      if (j.liga && ligas.indexOf(j.liga) < 0) ligas.push(j.liga);
    });
    ligas.sort(function (a, b) { return sinAcentos(a).localeCompare(sinAcentos(b)); });

    var selector = document.getElementById('filtro-liga-historico');
    ligas.forEach(function (liga) {
      var opcion = el('option', null, liga);
      opcion.value = liga;
      selector.appendChild(opcion);
    });
    selector.addEventListener('change', function () {
      historicoLiga = selector.value;
      historicoMostrarTodos = false;
      pintarHistorico();
    });

    var buscar = document.getElementById('buscar-historico');
    buscar.addEventListener('input', function () {
      historicoBusqueda = sinAcentos(buscar.value.trim());
      historicoMostrarTodos = false;
      pintarHistorico();
    });

    var ths = document.querySelectorAll('#tabla-historico thead th[data-orden]');
    Array.prototype.forEach.call(ths, function (th) {
      var boton = th.querySelector('button');
      if (!boton || !ORDEN_HISTORICO[th.dataset.orden]) return;
      boton.addEventListener('click', function () {
        var campo = th.dataset.orden;
        if (historicoColumna === campo) {
          historicoSentido = -historicoSentido;
        } else {
          historicoColumna = campo;
          historicoSentido = (campo === 'nombre' || campo === 'liga' ||
            campo === 'posicion' || campo === 'mejor_posicion') ? 1 : -1;
        }
        historicoMostrarTodos = false;
        pintarHistorico();
      });
    });

    document.getElementById('mostrar-historico').addEventListener('click', function () {
      historicoMostrarTodos = !historicoMostrarTodos;
      pintarHistorico();
    });
  }

  var TOP_SENTIMIENTO = 5;

  function barraSentimiento(valor, tope) {
    var caja = el('span', 'barra-sent');
    caja.title = 'Escala de -50 a +50; la barra crece desde el cero central';
    var barra = el('i', valor < 0 ? 'barra-sent__barra--neg' : 'barra-sent__barra--pos');
    barra.style.width = Math.max(1, Math.round(Math.abs(valor) / tope * 50)) + '%';
    caja.appendChild(barra);
    return caja;
  }

  function pintarSentimiento() {
    var lista = DATOS.sentimiento.acumulado.slice(0, TOP_SENTIMIENTO);
    var cuerpo = document.getElementById('cuerpo-sentimiento');
    cuerpo.textContent = '';
    if (!lista.length) {
      var trVacio = el('tr');
      var celdaVacia = el('td', null, 'Todavía no hay menciones guardadas para armar este top.');
      celdaVacia.colSpan = 3;
      trVacio.appendChild(celdaVacia);
      cuerpo.appendChild(trVacio);
      return;
    }
    var tope = Math.max.apply(null, lista.map(function (j) {
      return Math.abs(j.sentimiento_medio);
    }).concat([1]));

    lista.forEach(function (j) {
      var tr = el('tr');
      tr.appendChild(el('td', null, j.posicion));

      var nombre = el('td');
      nombre.appendChild(document.createTextNode(j.nombre));
      nombre.appendChild(el('small', null, j.club));
      tr.appendChild(nombre);

      var celda = el('td');
      var interior = el('div', 'celda-sent');
      interior.appendChild(barraSentimiento(j.sentimiento_medio, tope));
      interior.appendChild(el('b', j.sentimiento_medio < 0 ? 'neg' : 'pos',
        (j.sentimiento_medio > 0 ? '+' : '') + dec1.format(j.sentimiento_medio)));
      celda.appendChild(interior);
      tr.appendChild(celda);

      cuerpo.appendChild(tr);
    });
  }

  function cintaSentimiento() {
    var cinta = document.getElementById('cinta-sentimiento');
    cinta.textContent = '';
    var conDos = DATOS.sentimiento.acumulado.filter(function (j) { return j.fuentes === 2; }).length;
    [
      ['Jugadores medidos', String(DATOS.sentimiento.jugadores)],
      ['Mediciones', String(DATOS.sentimiento.mediciones)],
      ['Con ambas fuentes', conDos + ' de ' + DATOS.sentimiento.jugadores],
      ['Escala', '−50 a +50']
    ].forEach(function (par) {
      cinta.appendChild(itemCinta(par[0], par[1]));
    });
  }

  function pintarFeatures() {
    var lista = document.getElementById('features');
    if (!lista) return;
    lista.textContent = '';
    (DATOS.modelo.features || []).forEach(function (feature) {
      var etiqueta = NOMBRES_FEATURES[feature]
        || feature.replace(/^pos_/, '').replace(/_/g, ' ');
      var item = el('li', null, etiqueta);
      item.dataset.tipo = feature.indexOf('pos_') === 0 ? 'posicion' : 'estadistica';
      lista.appendChild(item);
    });
  }

  document.getElementById('generado').textContent = fecha(DATOS.generado).toLocaleDateString('es-AR', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'
  });

  pintarSelector();
  pintarRadar();
  pintarPuestos();
  conectarHistorico();
  pintarHistorico();
  cintaSentimiento();
  pintarSentimiento();
  pintarFeatures();
})();
