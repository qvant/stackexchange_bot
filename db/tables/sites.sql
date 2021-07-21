create table stackexchange_db.sites
(
    id serial primary key,
    api_site_parameter varchar(1024) not null,
    dt_created  timestamp with time zone default current_timestamp
);
create unique index u_sites_api_site_parameter on stackexchange_db.sites(api_site_parameter);
alter table stackexchange_db.sites owner to stackexchange_bot;