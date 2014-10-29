define(['settings'],
function (Settings) {
  return new Settings({
    datasources: {
      influxdb: {
        type: 'influxdb',
        url: "http://localhost:8086/db/locust",
        username: 'admin',
        password: 'admin',
        default: true
      },
      grafana: {
        type: 'influxdb',
        url: "http://localhost:8086/db/grafana",
        username: 'admin',
        password: 'admin',
        grafanaDB: true
      },
    },
    search: {
      max_results: 20
    },
    default_route: '/dashboard/file/locust.json',
    unsaved_changes_warning: true,
    playlist_timespan: "1m",
    admin: {
      password: ''
    },
    window_title_prefix: 'Grafana - ',
    plugins: {
      panels: [],
      dependencies: [],
    }
  });
});
